#!/usr/bin/env python3
"""List WeChat contacts or groups from a decrypted contact database."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact-db", required=True, type=Path)
    parser.add_argument("--kind", choices=("all", "group", "private"), default="all")
    parser.add_argument("--contains", default="", help="Case-insensitive name filter")
    parser.add_argument("--include-identifiers", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    with connect_readonly(args.contact_db) as database:
        rows = database.execute(
            "SELECT username, alias, remark, nick_name FROM contact"
        ).fetchall()

    needle = args.contains.casefold().strip()
    results = []
    for row in rows:
        identifier = row["username"] or ""
        kind = "group" if identifier.endswith("@chatroom") else "private"
        if args.kind != "all" and kind != args.kind:
            continue
        display_name = row["remark"] or row["nick_name"] or row["alias"] or identifier
        searchable = " ".join(
            str(row[key] or "") for key in ("remark", "nick_name", "alias")
        ).casefold()
        if needle and needle not in searchable:
            continue
        item = {"kind": kind, "name": display_name}
        if args.include_identifiers:
            item["identifier"] = identifier
        results.append(item)

    results.sort(key=lambda item: (item["kind"], item["name"].casefold()))
    if args.as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            suffix = f"\t{item['identifier']}" if "identifier" in item else ""
            print(f"{item['kind']}\t{item['name']}{suffix}")
    print(f"MATCHED_CHATS:{len(results)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
