"""Offline synthetic fixtures only; no protected keys or live databases."""
import hashlib
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import read_chat as reader


class ReaderTests(unittest.TestCase):
    def test_date_boundary_and_offset(self):
        tz = reader.tz_for('+08:00')
        self.assertEqual(reader.boundary('2026-01-01', tz),
                         reader.boundary('2025-12-31T16:00:00+00:00', tz))
        with self.assertRaises(ValueError):
            reader.boundary('2026-01-01T09:00', tz)

    def test_plain_and_quote_are_distinct(self):
        kind, content, details = reader.summarize(49,
            '<msg><appmsg><type>57</type><title>Use the new plan</title>'
            '<refermsg><displayname>Colleague</displayname><content>Old plan</content>'
            '</refermsg></appmsg></msg>')
        self.assertEqual((kind, content), ('quote', 'Use the new plan'))
        self.assertEqual(details['quoted']['content'], 'Old plan')

    def test_forwarded_history(self):
        xml = '<msg><appmsg><type>19</type><recorditem><![CDATA[<recordinfo><datalist>' \
              '<dataitem><sourcename>Other person</sourcename><datadesc>Earlier decision</datadesc>' \
              '</dataitem></datalist></recordinfo>]]></recorditem></appmsg></msg>'
        kind, _, details = reader.summarize(49, xml)
        self.assertEqual(kind, 'chat_history')
        self.assertEqual(details['forwarded'][0]['datadesc'], 'Earlier decision')

    def test_unparsed_media_not_claimed_read(self):
        self.assertEqual(reader.summarize(3, '')[:2], ('image', '[Image]'))
        self.assertIn('parse_warning', reader.summarize(49, '<broken>')[2])

    def test_wal_uses_only_last_commit(self):
        header = struct.pack('>IIIIII', 0x377f0682, 3007000, 4096, 0, 7, 8)
        state = reader.checksum(header, '<')
        wal = header + struct.pack('>II', *state)
        for number, commit, page in [(1, 1, b'B' * 4096), (1, 0, b'C' * 4096)]:
            frame = struct.pack('>IIII', number, commit, 7, 8)
            state = reader.checksum(frame[:8] + page, '<', state)
            wal += frame + struct.pack('>II', *state) + page
        merged, meta = reader.merge_committed_wal(b'A' * 4096, wal)
        self.assertEqual(merged, b'B' * 4096)
        self.assertEqual((meta['valid_frames'], meta['committed_frames']), (2, 1))

    def test_bad_wal_header(self):
        with self.assertRaises(ValueError):
            reader.merge_committed_wal(b'A' * 4096, b'bad')
        self.assertEqual(reader.merge_committed_wal(b'A', b'')[0], b'A')

    def test_multiple_shards_date_filter_and_dedup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chat = 'synthetic-project'
            table = 'Msg_' + hashlib.md5(chat.encode()).hexdigest()
            paths = []
            for index, rows in enumerate([
                [(9, 111, 100, 'first'), (2, 0, 90, 'too early')],
                [(8, 111, 100, 'first'), (1, 222, 100, 'second'), (10, 333, 120, 'too late')]]):
                path = root / f'part{index}.db'
                with closing(sqlite3.connect(path)) as conn, conn:
                    conn.execute('CREATE TABLE Name2Id (user_name TEXT)')
                    conn.execute("INSERT INTO Name2Id VALUES ('person')")
                    conn.execute(f'CREATE TABLE "{table}" (local_id,server_id,create_time,local_type,message_content,real_sender_id,sort_seq)')
                    conn.executemany(f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?,?)',
                        [(local, server, stamp, 1, body.encode(), 1, server or local) for local, server, stamp, body in rows])
                paths.append((path.name, path))
            result = reader.read_rows(paths, chat, {'person': 'Test Person'}, 100, 120, reader.tz_for('+08:00'))
            self.assertEqual([r['content'] for r in result], ['first', 'second'])
            self.assertEqual(result[0]['sender'], 'Test Person')
            with closing(reader.connect(paths[0][1])) as conn:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute('CREATE TABLE forbidden (a)')

    def test_output_and_snapshot_path_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = {'source_root': str(root), 'work_root': str(root / 'unsafe')}
            with self.assertRaises(ValueError):
                reader.private_run(profile)
            with self.assertRaises(ValueError):
                reader.snapshot_db(profile, '../escape.db', b'0' * 32, root.parent / 'output')


if __name__ == '__main__':
    unittest.main()
