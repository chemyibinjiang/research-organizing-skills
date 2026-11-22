"""Project-neutral read-only WeChat adapter using the established local helpers."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import uuid
import xml.etree.ElementTree as ET

SKILL = Path(__file__).resolve().parents[1]


def profile_path():
    return Path(os.environ['LOCALAPPDATA']) / 'Codex/communication-skills/profiles.json'


def load_profile(path, name):
    profile = json.loads(Path(path).read_text(encoding='utf-8-sig'))['wechat'][name]
    for directory in reversed(profile.get('runtime_paths', [])):
        sys.path.insert(0, str(Path(directory).expanduser()))
    return profile


def tz_for(offset):
    sign = -1 if offset.startswith('-') else 1
    hours, minutes = map(int, offset[1:].split(':'))
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def boundary(value, tz):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        if len(value) != 10:
            raise ValueError('Datetime boundaries require an explicit UTC offset')
        parsed = parsed.replace(tzinfo=tz)
    return parsed.timestamp()


def checksum(data, endian, state=(0, 0)):
    words = struct.unpack(endian + str(len(data) // 4) + 'I', data)
    a, b = state
    for i in range(0, len(words), 2):
        a = (a + words[i] + b) & 0xffffffff
        b = (b + words[i + 1] + a) & 0xffffffff
    return a, b


def merge_committed_wal(data, wal):
    meta = {'base_bytes': len(data), 'wal_bytes': len(wal),
            'valid_frames': 0, 'committed_frames': 0}
    if not wal:
        return data, meta
    if len(wal) < 32:
        raise ValueError('Short WAL; snapshot is not usable')
    magic, version, size = struct.unpack('>III', wal[:12])
    if magic not in (0x377f0682, 0x377f0683) or version != 3007000 or size != 4096:
        raise ValueError('Unsupported WAL format')
    endian = '<' if magic == 0x377f0682 else '>'
    state = checksum(wal[:24], endian)
    if state != struct.unpack('>II', wal[24:32]):
        raise ValueError('WAL header checksum mismatch')
    frames, commit_count, db_size = [], 0, 0
    for offset in range(32, len(wal) - 4119, 4120):
        header, page = wal[offset:offset + 24], wal[offset + 24:offset + 4120]
        if header[8:16] != wal[16:24]:
            break
        updated = checksum(header[:8] + page, endian, state)
        if updated != struct.unpack('>II', header[16:24]):
            break
        state = updated
        number, commit = struct.unpack('>II', header[:8])
        if number < 1:
            raise ValueError('Invalid WAL page number')
        frames.append((number, page))
        if commit:
            commit_count, db_size = len(frames), commit
    meta.update(valid_frames=len(frames), committed_frames=commit_count,
                ignored_tail_bytes=len(wal) - 32 - 4120 * len(frames))
    if commit_count:
        result = bytearray(data)
        if db_size * 4096 > len(data) + len(frames) * 4096:
            raise ValueError('Implausible committed database size')
        result.extend(bytes(max(0, db_size * 4096 - len(result))))
        for number, page in frames[:commit_count]:
            if number <= db_size:
                result[(number - 1) * 4096:number * 4096] = page
        data = bytes(result[:db_size * 4096])
    return data, meta


def connect(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def private_run(profile):
    root = Path(profile['work_root']).expanduser().resolve()
    source = Path(profile['source_root']).expanduser().resolve()
    if root == SKILL or SKILL in root.parents or root == source or source in root.parents:
        raise ValueError('Private output must be outside the skill and live database tree')
    root.mkdir(parents=True, exist_ok=True)
    run = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run.mkdir()
    return run


def snapshot_db(profile, relative, key, run):
    from decrypt_databases import decrypt_database
    root = Path(profile['source_root']).expanduser().resolve()
    source = (root / relative).resolve()
    if root not in source.parents:
        raise ValueError('Database path escapes source root')
    relative = source.relative_to(root)
    run = Path(run).resolve()
    if run == root or root in run.parents or run == SKILL or SKILL in run.parents:
        raise ValueError('Unsafe snapshot destination')
    wal_path = Path(str(source) + '-wal')
    for _ in range(5):
        first = source.read_bytes(), wal_path.read_bytes() if wal_path.exists() else b''
        second = source.read_bytes(), wal_path.read_bytes() if wal_path.exists() else b''
        if first == second:
            break
    else:
        raise RuntimeError('Database changed repeatedly during snapshot')
    data, meta = merge_committed_wal(*first)
    encrypted = run / 'committed-snapshot' / relative
    encrypted.parent.mkdir(parents=True, exist_ok=True)
    encrypted.write_bytes(data)
    target = run / 'decrypted' / relative
    if not decrypt_database(key, encrypted, target):
        raise RuntimeError('Decryption failed; do not recover credentials automatically')
    with closing(connect(target)) as conn:
        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise RuntimeError('Snapshot integrity check failed')
    meta.update(database=relative.as_posix(), sha256=hashlib.sha256(data).hexdigest(), integrity='ok')
    return target, meta


def summarize(raw_type, decoded):
    from export_group import summarize_content
    kind, content = summarize_content(raw_type, decoded)
    details = {}
    if raw_type & 0xffff == 49:
        try:
            root = ET.fromstring(decoded[decoded.index('<'):])
            app = root if root.tag == 'appmsg' else root.find('.//appmsg')
            if app is not None:
                subtype = int(app.findtext('type') or (raw_type >> 32))
                title = app.findtext('title') or ''
                if subtype == 57:
                    kind, content = 'quote', title
                    ref = app.find('refermsg')
                    details['quoted'] = {} if ref is None else {
                        k: ref.findtext(k) for k in ('displayname', 'createtime', 'content')}
                elif subtype == 19:
                    kind, content = 'chat_history', title or '[Forwarded history]'
                    record = app.findtext('recorditem')
                    details['forwarded'] = [] if not record else [
                        {k: item.findtext(k) for k in ('sourcename', 'sourcetime', 'datadesc', 'datatitle')}
                        for item in ET.fromstring(record).findall('.//dataitem')]
                else:
                    content = title or content
                    details['attachment_content_inspected'] = False
        except (ValueError, ET.ParseError):
            details['parse_warning'] = 'App message not fully parsed'
    return kind, content, details


def read_rows(paths, chat_id, names, since, before, tz):
    from export_group import decode_message
    table = 'Msg_' + hashlib.md5(chat_id.encode()).hexdigest()
    messages, seen = [], set()
    for label, path in paths:
        with closing(connect(path)) as conn:
            if not conn.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                continue
            rows = conn.execute(
                f'SELECT m.local_id,m.server_id,m.create_time,m.local_type,m.sort_seq,'
                f'hex(m.message_content) AS hex,n.user_name AS sender FROM "{table}" m '
                'LEFT JOIN Name2Id n ON n.rowid=m.real_sender_id '
                'WHERE m.create_time>=? AND m.create_time<? ORDER BY m.sort_seq,m.local_id',
                (since, before)).fetchall()
        for row in rows:
            identity = ('server', str(row['server_id'])) if row['server_id'] else (label, row['local_id'])
            if identity in seen:
                continue
            seen.add(identity)
            kind, content, details = summarize(int(row['local_type'] or 0), decode_message(row['hex']))
            messages.append(dict(time=datetime.fromtimestamp(row['create_time'], tz).isoformat(),
                                 sender=names.get(row['sender'], row['sender'] or '[Unknown]'),
                                 sender_id=row['sender'], sort_seq=row['sort_seq'],
                                 create_time=row['create_time'], raw_type=int(row['local_type'] or 0),
                                 kind=kind, content=content, details=details,
                                 server_id=row['server_id'], local_id=row['local_id'], database=label))
    return sorted(messages, key=lambda m: (m['time'], m['sort_seq'] or 0, m['database'], m['local_id']))


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['contacts', 'read'])
    parser.add_argument('--config', type=Path, default=profile_path())
    parser.add_argument('--profile', required=True)
    parser.add_argument('--contains')
    parser.add_argument('--chat')
    parser.add_argument('--kind', choices=['group', 'private'])
    parser.add_argument('--since')
    parser.add_argument('--before')
    args = parser.parse_args()
    if args.mode == 'contacts' and not args.contains:
        parser.error('contacts requires --contains; bulk listing is not the default')
    if args.mode == 'read' and not (args.chat and args.since):
        parser.error('read requires --chat and --since')
    profile = load_profile(args.config, args.profile)
    tz = tz_for(profile['timezone_offset'])
    since = boundary(args.since, tz) if args.since else None
    before = boundary(args.before, tz) if args.before else datetime.now(tz).timestamp()
    if since is not None and since >= before:
        parser.error('--since must precede --before')
    run = private_run(profile)
    from decrypt_databases import unprotect_with_dpapi
    key = unprotect_with_dpapi(Path(profile['key_path']).read_bytes())
    if len(key) != 32:
        raise ValueError('Existing protected key is not valid')
    contact, meta = snapshot_db(profile, 'contact/contact.db', key, run)
    with closing(connect(contact)) as conn:
        contacts = [dict(r) for r in conn.execute('SELECT username,remark,nick_name FROM contact')]
    selected = [r for r in contacts if not args.kind or
                r['username'].endswith('@chatroom') == (args.kind == 'group')]
    if args.mode == 'contacts':
        selected = [r for r in selected if args.contains.casefold() in
                    ' '.join(str(v or '') for v in r.values()).casefold()]
        print(json.dumps({'matches': selected, 'run': str(run)}, ensure_ascii=False))
        return
    selected = [r for r in selected if args.chat in (r['username'], r['remark'], r['nick_name'])]
    if len(selected) != 1:
        raise ValueError(f'Expected one exact conversation; found {len(selected)}')
    names = {r['username']: r['remark'] or r['nick_name'] or r['username'] for r in contacts}
    root = Path(profile['source_root']).resolve()
    shards = sorted((root / 'message').glob('message_[0-9]*.db'))
    if not shards:
        raise RuntimeError('No message shards found; schema/layout needs inspection')
    paths, metadata = [], [meta]
    for source in shards:
        relative = source.relative_to(root).as_posix()
        path, meta = snapshot_db(profile, relative, key, run)
        paths.append((relative, path))
        metadata.append(meta)
    del key
    messages = read_rows(paths, selected[0]['username'], names, since, before, tz)
    result = dict(checked_at=datetime.now(tz).isoformat(), chat=names[selected[0]['username']],
                  since=datetime.fromtimestamp(since, tz).isoformat(),
                  before=datetime.fromtimestamp(before, tz).isoformat(), messages=messages,
                  count=len(messages), kinds=dict(Counter(m['kind'] for m in messages)),
                  snapshots=metadata, media_contents_inspected=False)
    (run / 'messages.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (run / 'messages.txt').write_text('\n'.join(
        f"[{m['time']}] {m['sender']} ({m['kind']}): {m['content']} "
        + (json.dumps(m['details'], ensure_ascii=False) if m['details'] else '')
        for m in messages), encoding='utf-8')
    print(json.dumps({'run': str(run), 'count': len(messages), 'kinds': result['kinds']}))


if __name__ == '__main__':
    main()
