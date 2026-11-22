#!/usr/bin/env python3
"""Map one WeChat 4.x group's resource messages to local attachment files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


FILE_SUFFIXES = {
    ".7z",
    ".avi",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".md",
    ".mov",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".txt",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}
HEX32_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--resource-db", required=True, type=Path)
    parser.add_argument("--hardlink-db", required=True, type=Path)
    parser.add_argument("--wechat-account-root", required=True, type=Path)
    parser.add_argument("--messages-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ValueError("invalid protobuf varint")


def protobuf_strings(data: bytes, depth: int = 0) -> list[str]:
    """Collect readable strings from protobuf-like packed resource metadata."""
    if not data or depth > 5:
        return []
    strings: list[str] = []
    offset = 0
    try:
        while offset < len(data):
            key, offset = read_varint(data, offset)
            wire_type = key & 7
            if wire_type == 0:
                _, offset = read_varint(data, offset)
            elif wire_type == 1:
                offset += 8
            elif wire_type == 2:
                size, offset = read_varint(data, offset)
                if size < 0 or offset + size > len(data):
                    break
                chunk = data[offset : offset + size]
                offset += size
                try:
                    decoded = chunk.decode("utf-8")
                except UnicodeDecodeError:
                    decoded = ""
                if decoded and all(char.isprintable() or char in "\r\n\t" for char in decoded):
                    strings.append(decoded.strip())
                strings.extend(protobuf_strings(chunk, depth + 1))
            elif wire_type == 5:
                offset += 4
            else:
                break
    except (IndexError, ValueError):
        pass
    return [item for item in strings if item]


def packed_strings(value: Any) -> list[str]:
    if value is None or value == 0 or value == "0":
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if len(stripped) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", stripped):
            try:
                return protobuf_strings(bytes.fromhex(stripped))
            except ValueError:
                return [stripped]
        return [stripped]
    return protobuf_strings(bytes(value))


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def file_names_from(strings: Iterable[str]) -> list[str]:
    names = []
    for value in strings:
        candidate = value.strip().replace("\\", "/").rsplit("/", 1)[-1]
        if Path(candidate).suffix.lower() in FILE_SUFFIXES:
            names.append(candidate)
    return unique(names)


def hash_names_from(strings: Iterable[str]) -> list[str]:
    return unique(value.lower() for value in strings if HEX32_RE.fullmatch(value.strip()))


def index_files(root: Path) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = defaultdict(list)
    if not root.exists():
        return result
    for path in root.rglob("*"):
        if path.is_file():
            result[path.name.casefold()].append(path.resolve())
    return result


def choose_file(paths: list[Path], expected_sizes: set[int]) -> Path | None:
    candidates = [p for p in paths if not expected_sizes or p.stat().st_size in expected_sizes]
    return candidates[0] if len(candidates) == 1 else None


def file_hardlinks(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    rows = connection.execute(
        "SELECT f.file_name, f.file_size, f.md5, f.type, f.modify_time, "
        "d.username AS dir_name "
        "FROM file_hardlink_info_v4 f "
        "LEFT JOIN dir2id d ON d.rowid=f.dir1"
    ).fetchall()
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[row["file_name"].casefold()].append(dict(row))
    return result


def load_message_export(path: Path) -> tuple[dict[str, dict], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    chat_name = payload.get("chat") or payload.get("group") or payload.get("peer_name") or "WeChat chat"
    index = {'server': defaultdict(list), 'fallback': defaultdict(list)}
    for item in payload['messages']:
        server_id = int(item.get('server_id') or 0)
        if server_id:
            index['server'][server_id].append(item)
        if item.get('create_time') is not None and item.get('raw_type') is not None:
            key = (int(item['local_id']), int(item['create_time']), int(item['raw_type']))
            index['fallback'][key].append(item)
    return index, chat_name


def match_message(index, row):
    server_id = int(row['message_svr_id'] or 0)
    candidates = index['server'].get(server_id, []) if server_id else []
    if not candidates:
        key = (int(row['message_local_id']), int(row['message_create_time']), int(row['message_local_type'] or 0))
        candidates = [item for item in index['fallback'].get(key, [])
                      if not server_id or not item.get('server_id')]
    # A local ID alone is not unique across shards; ambiguous matches stay unresolved.
    return candidates[0] if len(candidates) == 1 else None


def output_size(path: Path | None) -> int | None:
    return path.stat().st_size if path and path.exists() else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    account_root = args.wechat_account_root.resolve()
    skill_root = Path(__file__).resolve().parents[1]
    output_root = args.output_dir.resolve()
    if output_root == account_root or account_root in output_root.parents or output_root == skill_root or skill_root in output_root.parents:
        raise ValueError('Attachment manifests must be outside account and skill trees')
    if any(account_root in p.resolve().parents for p in (args.hardlink_db, args.resource_db)):
        raise ValueError('Use private database snapshots, not live account databases')
    message_map, group_name = load_message_export(args.messages_json)
    chat_hash = hashlib.md5(args.group_id.encode("utf-8")).hexdigest()
    file_root = args.wechat_account_root / "msg" / "file"
    attach_root = args.wechat_account_root / "msg" / "attach" / chat_hash
    local_files = index_files(file_root)
    local_images = index_files(attach_root)

    with closing(connect_readonly(args.hardlink_db)) as hardlink_db:
        hardlinks = file_hardlinks(hardlink_db)

    with closing(connect_readonly(args.resource_db)) as resource_db:
        chat_row = resource_db.execute(
            "SELECT rowid FROM ChatName2Id WHERE user_name=?", (args.group_id,)
        ).fetchone()
        if not chat_row:
            raise SystemExit(f"Group not found in resource DB: {args.group_id}")
        rows = resource_db.execute(
            "SELECT i.message_id, i.message_local_id, i.message_svr_id, "
            "i.message_local_type, i.message_create_time, i.packed_info AS info_packed, "
            "d.resource_id, d.type AS detail_type, d.size, d.status, "
            "d.data_index, d.packed_info AS detail_packed "
            "FROM MessageResourceInfo i "
            "LEFT JOIN MessageResourceDetail d ON d.message_id=i.message_id "
            "WHERE i.chat_id=? "
            "ORDER BY i.message_create_time, i.message_local_id, d.resource_id",
            (int(chat_row["rowid"]),),
        ).fetchall()

    matched = [(row, match_message(message_map, row)) for row in rows]
    selected_rows = [row for row, message in matched if message is not None]
    source_messages = {int(row['message_id']): message for row, message in matched if message is not None}
    grouped: dict[tuple[int, int, int, int], list[sqlite3.Row]] = defaultdict(list)
    for row in selected_rows:
        logical_key = (
            int(row["message_local_id"]),
            int(row["message_svr_id"] or 0),
            int(row["message_local_type"] or 0),
            int(row["message_create_time"]),
        )
        grouped[logical_key].append(row)

    manifest: list[dict[str, Any]] = []
    for _logical_key, detail_rows in grouped.items():
        first = detail_rows[0]
        source_message_ids = sorted({int(row["message_id"]) for row in detail_rows})
        local_id = int(first["message_local_id"])
        raw_type = int(first["message_local_type"] or 0)
        low_type = raw_type & 0xFFFF
        subtype = raw_type >> 32
        message = source_messages[int(first['message_id'])]
        timestamp = datetime.fromtimestamp(int(first["message_create_time"])).isoformat(
            sep=" ", timespec="seconds"
        )
        detail_strings: list[str] = []
        detail_records: list[dict[str, Any]] = []
        detail_seen: set[tuple[Any, ...]] = set()
        expected_sizes: set[int] = set()
        for row in detail_rows:
            strings = unique(
                packed_strings(row["data_index"])
                + packed_strings(row["detail_packed"])
                + packed_strings(row["info_packed"])
            )
            detail_strings.extend(strings)
            size = int(row["size"] or 0)
            if size:
                expected_sizes.add(size)
            detail_key = (
                row["detail_type"],
                size,
                row["status"],
                str(row["data_index"]),
                bytes(row["detail_packed"] or b""),
            )
            if detail_key in detail_seen:
                continue
            detail_seen.add(detail_key)
            detail_records.append(
                {
                    "resource_id": row["resource_id"],
                    "detail_type": row["detail_type"],
                    "size": size,
                    "status": row["status"],
                    "metadata_strings": strings,
                }
            )

        names = file_names_from(detail_strings)
        hashes = hash_names_from(detail_strings)
        local_paths: list[Path] = []
        md5_values: list[str] = []
        note = ""

        if low_type == 3:
            kind = "image"
            for image_hash in hashes:
                for suffix in (".dat", "_t.dat", "_h.dat"):
                    local_paths.extend(local_images.get((image_hash + suffix).casefold(), []))
            local_paths = list(dict.fromkeys(local_paths))
            status = "available_encrypted" if local_paths else "missing_local_cache"
            note = "V2 encrypted WeChat image cache; requires a separate decoded copy to view."
        elif low_type == 49 and subtype == 6:
            kind = "file"
            for name in names:
                links = hardlinks.get(name.casefold(), [])
                md5_values.extend(str(item["md5"]) for item in links if item.get("md5"))
                path = choose_file(local_files.get(name.casefold(), []), expected_sizes)
                if path:
                    local_paths.append(path)
            local_paths = list(dict.fromkeys(local_paths))
            status = "candidate_plain" if local_paths else "missing_or_ambiguous_local_file"
            note = "Candidate matched by filename/size; confirm content and source before relying on it."
        elif low_type == 49 and subtype == 19:
            kind = "chat_history"
            status = "inline_reference_only"
            note = "Merged-chat references are recorded, but not exposed as standalone files."
        elif low_type == 49 and subtype == 36:
            kind = "link"
            status = "link_no_local_attachment"
            note = "Link metadata only; no standalone local attachment is expected."
        else:
            kind = f"type_{low_type}_subtype_{subtype}"
            status = "unclassified"

        manifest.append(
            {
                "timestamp": timestamp,
                "sender": message.get("sender", ""),
                "sender_wxid": message.get("sender_id", message.get("sender_wxid", "")),
                "database": message.get("database", ""),
                "local_id": local_id,
                "server_id": int(first["message_svr_id"] or 0),
                "resource_db_message_ids": source_message_ids,
                "resource_db_duplicate_count": max(0, len(source_message_ids) - 1),
                "kind": kind,
                "subtype": subtype,
                "message_summary": message.get("content", ""),
                "original_names": names,
                "resource_hashes": hashes,
                "expected_sizes": sorted(expected_sizes),
                "local_paths": [str(path) for path in local_paths],
                "local_sizes": [output_size(path) for path in local_paths],
                "hardlink_md5": unique(md5_values),
                "status": status,
                "note": note,
                "resource_details": detail_records,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_chat_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", group_name).strip(" ._")
    stem = f"wechat_{safe_chat_name}_attachments_{stamp}"
    json_path = args.output_dir / f"{stem}.json"
    csv_path = args.output_dir / f"{stem}.csv"
    md_path = args.output_dir / f"{stem}.md"
    status_counts = Counter(item["status"] for item in manifest)
    kind_counts = Counter(item["kind"] for item in manifest)
    raw_resource_count = len({int(row["message_id"]) for row in selected_rows})
    duplicate_record_count = raw_resource_count - len(manifest)
    payload = {
        "group": group_name,
        "group_id": args.group_id,
        "chat_hash": chat_hash,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "raw_resource_record_count": raw_resource_count,
        "logical_resource_count": len(manifest),
        "duplicate_resource_records_suppressed": duplicate_record_count,
        "kind_counts": dict(kind_counts),
        "status_counts": dict(status_counts),
        "items": manifest,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "timestamp",
        "sender",
        "local_id",
        "server_id",
        "kind",
        "subtype",
        "original_names",
        "resource_hashes",
        "expected_sizes",
        "local_paths",
        "status",
        "note",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in manifest:
            writer.writerow(
                {
                    key: " | ".join(str(value) for value in item[key])
                    if isinstance(item[key], list)
                    else item[key]
                    for key in fieldnames
                }
            )

    lines = [
        f"# {group_name} 附件映射清单",
        "",
        f"- 逻辑资源：{len(manifest)} 条",
        f"- 原始资源记录：{raw_resource_count} 条（去除重复记录 {duplicate_record_count} 条）",
        f"- 类型：{json.dumps(dict(kind_counts), ensure_ascii=False)}",
        f"- 状态：{json.dumps(dict(status_counts), ensure_ascii=False)}",
        "- 说明：微信 V2 图片仍为加密缓存；文档等普通文件可直接打开。",
        "",
        "## 明细",
        "",
        "| 时间 | 发送人 | 类型 | 文件名/资源 | 状态 | 本地路径 |",
        "|---|---|---|---|---|---|",
    ]
    for item in manifest:
        labels = item["original_names"] or item["resource_hashes"] or [item["message_summary"]]
        paths = item["local_paths"] or [""]
        label_text = "<br>".join(str(value).replace("|", "\\|") for value in labels)
        path_text = "<br>".join(str(value).replace("|", "\\|") for value in paths)
        lines.append(
            f"| {item['timestamp']} | {item['sender']} | {item['kind']} | "
            f"{label_text} | {item['status']} | {path_text} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"LOGICAL_RESOURCES:{len(manifest)}")
    print(f"RAW_RESOURCE_RECORDS:{raw_resource_count}")
    print(f"DUPLICATES_SUPPRESSED:{duplicate_record_count}")
    print(f"KIND_COUNTS:{json.dumps(dict(kind_counts), ensure_ascii=False)}")
    print(f"STATUS_COUNTS:{json.dumps(dict(status_counts), ensure_ascii=False)}")
    print(f"JSON:{json_path.resolve()}")
    print(f"CSV:{csv_path.resolve()}")
    print(f"MD:{md_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
