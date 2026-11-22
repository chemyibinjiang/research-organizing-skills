#!/usr/bin/env python3
"""Decode mapped WeChat V2 image caches without modifying source files."""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


V2_MAGIC = b"\x07\x08\x56\x32\x08\x07"


def aes_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return decryptor.update(data) + decryptor.finalize()


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def unprotect_with_dpapi(data: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    input_blob = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--wechat-account-root", required=True, type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def image_magic(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:3] == b"GIF":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] == b"wxgf":
        return "wxgf"
    return None


def encrypted_probe(path: Path) -> bytes:
    with path.open("rb") as handle:
        head = handle.read(31)
    if head[:6] != V2_MAGIC or len(head) < 31:
        raise ValueError(f"Not a usable V2 image cache: {path}")
    return head[15:31]


def validate_aes_key(key: str, probe: bytes) -> bool:
    try:
        return image_magic(aes_ecb_decrypt(key.encode("ascii"), probe)) is not None
    except (UnicodeEncodeError, ValueError):
        return False


def load_existing_key(key_path: Path, probe_path: Path) -> tuple[str, int, str]:
    if not key_path.is_file():
        raise FileNotFoundError('Existing protected image key is required; no recovery attempted')
    probe = encrypted_probe(probe_path)
    payload = json.loads(unprotect_with_dpapi(key_path.read_bytes()).decode("utf-8"))
    aes_key = str(payload["aes_key"])
    xor_key = int(payload["xor_key"])
    if not 0 <= xor_key <= 255 or not validate_aes_key(aes_key, probe):
        raise ValueError('Existing image key failed validation; no replacement attempted')
    return aes_key, xor_key, 'dpapi_cache'


def aligned_aes_block_size(aes_size: int) -> int:
    return aes_size + (16 - aes_size % 16) if aes_size % 16 else aes_size + 16


def decrypt_v2(path: Path, aes_key: str, xor_key: int) -> bytes:
    data = path.read_bytes()
    if data[:6] != V2_MAGIC:
        raise ValueError("Unsupported image cache format")
    aes_size, xor_size = struct.unpack_from("<LL", data, 6)
    aes_block_size = aligned_aes_block_size(aes_size)
    offset = 15
    aes_data = data[offset : offset + aes_block_size]
    offset += aes_block_size
    raw_data = data[offset : len(data) - xor_size]
    xor_data = data[len(data) - xor_size :]
    plaintext = aes_ecb_decrypt(aes_key.encode("ascii"), aes_data)
    pad = plaintext[-1] if plaintext else 0
    if 1 <= pad <= 16 and plaintext[-pad:] == bytes([pad]) * pad:
        plaintext = plaintext[:-pad]
    return plaintext + raw_data + bytes(byte ^ xor_key for byte in xor_data)


def ffmpeg_executable() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def wxgf_to_jpg(data: bytes) -> bytes | None:
    ffmpeg = ffmpeg_executable()
    start = data.find(b"\x00\x00\x00\x01")
    if not ffmpeg or start < 0:
        return None
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "source.hevc"
        target = Path(temp_dir) / "target.jpg"
        source.write_bytes(data[start:])
        result = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(source), "-frames:v", "1", str(target)],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0 and target.is_file():
            output = target.read_bytes()
            if output[:3] == b"\xff\xd8\xff":
                return output
    return None


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", value).strip(" ._")
    return cleaned[:60] or "unknown"


def choose_source(paths: list[str]) -> Path | None:
    candidates = [Path(value) for value in paths if Path(value).is_file()]
    if not candidates:
        return None
    for path in candidates:
        if not path.name.endswith(("_t.dat", "_h.dat")):
            return path
    for path in candidates:
        if path.name.endswith("_h.dat"):
            return path
    return candidates[0]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    image_items = [item for item in manifest["items"] if item["kind"] == "image"]
    sources = [(item, choose_source(item["local_paths"])) for item in image_items]
    probe_path = next((path for _, path in sources if path), None)
    if probe_path is None:
        raise SystemExit("No mapped image cache is available")

    account_root = args.wechat_account_root.resolve()
    output_root = args.output_dir.resolve()
    skill_root = Path(__file__).resolve().parents[1]
    if output_root == account_root or account_root in output_root.parents or output_root == skill_root or skill_root in output_root.parents:
        raise ValueError('Decoded copies must be outside the account and skill trees')
    if any(path and account_root not in path.resolve().parents for _, path in sources):
        raise ValueError('Image cache source is outside the selected account')
    aes_key, xor_key, key_source = load_existing_key(args.key_file.resolve(), probe_path)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    decoded: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    for item, source in sources:
        resource_hash = (
            item.get("resource_hashes", [""])[0]
            if item.get("resource_hashes")
            else (source.stem.removesuffix("_t").removesuffix("_h") if source else "")
        )
        record = {
            "timestamp": item["timestamp"],
            "sender": item["sender"],
            "local_id": item["local_id"],
            "resource_hash": resource_hash,
            "source": str(source) if source else "",
            "output": "",
            "format": "",
            "status": "",
        }
        if source is None:
            record["status"] = "missing_source"
            status_counts[record["status"]] += 1
            decoded.append(record)
            continue
        try:
            data = decrypt_v2(source, aes_key, xor_key)
            image_format = image_magic(data)
            if image_format == "wxgf":
                jpg = wxgf_to_jpg(data)
                if jpg is not None:
                    data = jpg
                    image_format = "jpg"
                else:
                    image_format = "wxgf"
            if image_format is None:
                raise ValueError("Decrypted data has an unknown image signature")
            date_part = item["timestamp"].replace("-", "").replace(":", "").replace(" ", "_")
            filename = (
                f"{date_part}_{int(item['local_id']):04d}_{resource_hash[:10]}_"
                f"{safe_name(item['sender'])}."
                f"{image_format}"
            )
            output = args.output_dir / filename
            output.write_bytes(data)
            record.update(
                {
                    "output": str(output.resolve()),
                    "format": image_format,
                    "status": "decoded",
                }
            )
        except Exception as error:
            record["status"] = "decode_failed"
            record["error"] = str(error)
        status_counts[record["status"]] += 1
        decoded.append(record)

    index_path = args.output_dir / "decoded_image_index.json"
    index_path.write_text(
        json.dumps(
            {
                "group": manifest["group"],
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "key_source": key_source,
                "image_count": len(decoded),
                "status_counts": dict(status_counts),
                "items": decoded,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"IMAGES:{len(decoded)}")
    print(f"STATUS_COUNTS:{json.dumps(dict(status_counts), ensure_ascii=False)}")
    print(f"KEY_SOURCE:{key_source}")
    print(f"INDEX:{index_path.resolve()}")
    return 0 if not status_counts.get("decode_failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
