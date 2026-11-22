#!/usr/bin/env python3
"""Decrypt selected local WeChat databases using a DPAPI-protected raw key."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
from ctypes import wintypes
from pathlib import Path

from Crypto.Cipher import AES


PAGE_SIZE = 4096
RESERVE_SIZE = 80
SALT_SIZE = 16


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def unprotect_with_dpapi(blob: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(blob)
    input_blob = DataBlob(len(blob), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
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
        kernel32.LocalFree(output_blob.pbData)


def decrypt_database(raw_key: bytes, source: Path, destination: Path) -> bool:
    data = source.read_bytes()
    if len(data) < PAGE_SIZE or len(data) % PAGE_SIZE:
        return False

    salt = data[:SALT_SIZE]
    encryption_key = hashlib.pbkdf2_hmac("sha512", raw_key, salt, 256000, 32)
    reserve_start = PAGE_SIZE - RESERVE_SIZE
    first_iv = data[reserve_start : reserve_start + 16]
    first_plaintext = AES.new(encryption_key, AES.MODE_CBC, first_iv).decrypt(
        data[SALT_SIZE:reserve_start]
    )
    if not (
        first_plaintext[0] == 0x10
        and first_plaintext[1] == 0x00
        and first_plaintext[4] == 0x50
        and first_plaintext[5] == 0x40
        and first_plaintext[7] == 0x20
    ):
        return False

    output = bytearray(b"SQLite format 3\x00")
    output += first_plaintext + data[reserve_start:PAGE_SIZE]
    for index in range(1, len(data) // PAGE_SIZE):
        page = data[index * PAGE_SIZE : (index + 1) * PAGE_SIZE]
        iv = page[reserve_start : reserve_start + 16]
        output += AES.new(encryption_key, AES.MODE_CBC, iv).decrypt(
            page[:reserve_start]
        )
        output += page[reserve_start:]

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(output)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--database", action="append", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    raw_key = unprotect_with_dpapi(args.key.resolve().read_bytes())
    if len(raw_key) != 32:
        raise SystemExit("Protected key did not contain a 32-byte WeChat key")

    failures = 0
    for relative_name in args.database:
        relative_path = Path(relative_name)
        source = (source_root / relative_path).resolve()
        if source_root not in source.parents:
            raise SystemExit(f"Database path escapes source root: {relative_name}")
        destination = output_root / relative_path
        if decrypt_database(raw_key, source, destination):
            print(f"DECRYPTED:{relative_path}")
        else:
            failures += 1
            print(f"FAILED:{relative_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
