#!/usr/bin/env python3
"""Export one WeChat group from decrypted WeChat 4.x databases."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import zstandard


TYPE_LABELS = {
    1: "text",
    3: "image",
    34: "audio",
    42: "contact_card",
    43: "video",
    47: "sticker",
    48: "location",
    49: "link_or_file",
    50: "call",
    10000: "system",
    10002: "recall",
}

TYPE_49_LABELS = {
    1: "Link",
    3: "Music",
    4: "Video Link",
    5: "File",
    6: "MiniApp",
    8: "Location",
    17: "Live Location",
    19: "Chat History",
    21: "MiniApp",
    33: "MiniApp",
    36: "Link",
    57: "Quote",
}


def connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def decode_message(hex_value: str) -> str:
    if not hex_value:
        return ""
    raw = bytes.fromhex(hex_value)
    compressed = raw.startswith(b"\x28\xb5\x2f\xfd")
    if compressed:
        raw = zstandard.ZstdDecompressor().decompress(raw)
    text = raw.decode("utf-8", errors="replace")
    prefix = re.match(r"^[^\s:]{1,80}:[\n ]", text)
    if prefix and (compressed or text.startswith("wxid_")):
        text = text[prefix.end() :]
    return text.strip()


def first_xml_value(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text)
    if not match:
        return ""
    value = match.group(1).strip()
    cdata = re.fullmatch(r"<!\[CDATA\[([\s\S]*?)\]\]>", value)
    return html.unescape(cdata.group(1) if cdata else value).strip()


def summarize_content(raw_type: int, decoded: str) -> tuple[str, str]:
    normalized_type = raw_type & 0xFFFF
    type_name = TYPE_LABELS.get(normalized_type, f"type_{normalized_type}")
    if normalized_type == 1:
        return type_name, decoded
    if normalized_type == 3:
        return type_name, "[Image]"
    if normalized_type == 34:
        duration = re.search(r"length=[\"'](\d+)[\"']", decoded)
        if duration:
            seconds = max(1, int(duration.group(1)) // 1000)
            return type_name, f"[Audio {seconds}s]"
        return type_name, "[Audio]"
    if normalized_type == 42:
        return type_name, "[Contact Card]"
    if normalized_type == 43:
        return type_name, "[Video]"
    if normalized_type == 47:
        return type_name, "[Sticker]"
    if normalized_type == 48:
        return type_name, "[Location]"
    if normalized_type == 50:
        return type_name, "[Call]"
    if normalized_type == 10000:
        if decoded.lstrip().startswith("<"):
            system_type = re.search(r'<sysmsg[^>]*type=["\']([^"\']+)', decoded)
            label = system_type.group(1) if system_type else "event"
            return type_name, f"[System message: {label}]"
        return type_name, decoded or "[System message]"
    if normalized_type == 10002:
        return type_name, decoded or "[Message recalled]"
    if normalized_type == 49:
        subtype = raw_type >> 32
        label = TYPE_49_LABELS.get(subtype, "Link/File")
        title = first_xml_value(decoded, "title")
        if subtype == 57:
            refer_name = first_xml_value(decoded, "displayname")
            refer_content = first_xml_value(decoded, "content")
            quote = f" [reply to {refer_name}: {refer_content[:100]}]" if refer_name else ""
            return "quote", (title or "[Quote]") + quote
        if subtype == 19:
            return "chat_history", "[Chat History]"
        return type_name, f"[{label}{': ' + title if title else ''}]"
    return type_name, decoded or f"[{type_name}]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True)
    parser.add_argument("--contact-db", required=True, type=Path)
    parser.add_argument("--message-db", required=True, type=Path)
    parser.add_argument("--my-wxid", required=True)
    parser.add_argument("--my-name", default="我")
    parser.add_argument("--since", help="Include messages on/after this ISO date or datetime")
    parser.add_argument("--before", help="Include messages before this ISO date or datetime")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def boundary_timestamp(value: str | None) -> float | None:
    return datetime.fromisoformat(value).timestamp() if value else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    with connect_readonly(args.contact_db) as contact_db:
        contacts = {
            row["username"]: row["remark"] or row["nick_name"] or row["username"]
            for row in contact_db.execute(
                "SELECT username, remark, nick_name FROM contact"
            )
        }
        group_rows = contact_db.execute(
            "SELECT username, remark, nick_name FROM contact "
            "WHERE remark = ? OR nick_name = ?",
            (args.group, args.group),
        ).fetchall()
    if len(group_rows) != 1:
        raise SystemExit(f"Expected one exact group match, found {len(group_rows)}")

    group_id = group_rows[0]["username"]
    table_name = "Msg_" + hashlib.md5(group_id.encode("utf-8")).hexdigest()
    with connect_readonly(args.message_db) as message_db:
        table_exists = message_db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        ).fetchone()
        if not table_exists:
            raise SystemExit(f"Message table not found: {table_name}")
        rows = message_db.execute(
            f'SELECT m.local_id, m.server_id, m.local_type, m.sort_seq, '
            f'm.create_time, m.real_sender_id, hex(m.message_content) AS message_hex, '
            f'n.user_name AS sender_wxid '
            f'FROM "{table_name}" m '
            f'LEFT JOIN Name2Id n ON n.rowid = m.real_sender_id '
            f'ORDER BY m.sort_seq ASC, m.local_id ASC'
        ).fetchall()

    since = boundary_timestamp(args.since)
    before = boundary_timestamp(args.before)
    rows = [
        row
        for row in rows
        if (since is None or int(row["create_time"]) >= since)
        and (before is None or int(row["create_time"]) < before)
    ]

    messages = []
    sender_counts: Counter[str] = Counter()
    for row in rows:
        sender_wxid = row["sender_wxid"] or ""
        is_self = sender_wxid == args.my_wxid
        normalized_type = int(row["local_type"] or 0) & 0xFFFF
        if normalized_type in (10000, 10002):
            sender = "系统"
        else:
            sender = (
                args.my_name
                if is_self
                else contacts.get(sender_wxid, sender_wxid or "未知发送者")
            )
        decoded = decode_message(row["message_hex"] or "")
        message_type, content = summarize_content(int(row["local_type"] or 0), decoded)
        timestamp = datetime.fromtimestamp(int(row["create_time"]))
        item = {
            "timestamp": timestamp.isoformat(sep=" ", timespec="seconds"),
            "sender": sender,
            "sender_wxid": sender_wxid,
            "is_self": is_self,
            "message_type": message_type,
            "content": content,
            "local_id": row["local_id"],
            "server_id": row["server_id"],
        }
        messages.append(item)
        sender_counts[sender] += 1

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_group = re.sub(r'[^\w.-]+', "_", args.group, flags=re.UNICODE).strip("._")
    stem = f"wechat_group_{safe_group}_{stamp}"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    md_path = output_dir / f"{stem}.md"

    payload = {
        "group": args.group,
        "group_id": group_id,
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "message_count": len(messages),
        "first_message_at": messages[0]["timestamp"] if messages else None,
        "last_message_at": messages[-1]["timestamp"] if messages else None,
        "sender_counts": dict(sender_counts.most_common()),
        "messages": messages,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "timestamp",
        "sender",
        "sender_wxid",
        "is_self",
        "message_type",
        "content",
        "local_id",
        "server_id",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(messages)

    lines = [
        f"# {args.group} 微信群记录",
        "",
        f"- 群内部 ID：`{group_id}`",
        f"- 消息数：{len(messages)}",
        f"- 时间范围：{payload['first_message_at']} 至 {payload['last_message_at']}",
        "",
        "## 聊天记录",
        "",
    ]
    current_date = None
    for item in messages:
        date_part, time_part = item["timestamp"].split(" ", 1)
        if date_part != current_date:
            lines.extend((f"### {date_part}", ""))
            current_date = date_part
        content = item["content"].replace("\r\n", "\n").replace("\n", "  \n  ")
        lines.append(f"- `{time_part}` **{item['sender']}**：{content}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"EXPORTED_MESSAGES:{len(messages)}")
    print(f"JSON:{json_path}")
    print(f"CSV:{csv_path}")
    print(f"MARKDOWN:{md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
