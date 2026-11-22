"""Synthetic attachment identities and stubbed key validation; no real keys."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import decode_group_images as images
import map_group_attachments as mapper


class AttachmentTests(unittest.TestCase):
    def test_missing_image_key_never_created(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'missing.dpapi'
            with self.assertRaises(FileNotFoundError):
                images.load_existing_key(key, Path(directory) / 'unused.dat')
            self.assertFalse(key.exists())

    def test_invalid_image_key_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'synthetic.dpapi'
            key.write_bytes(b'synthetic-protected-data')
            with patch.object(images, 'encrypted_probe', return_value=b'0' * 16), \
                 patch.object(images, 'unprotect_with_dpapi', return_value=b'{"aes_key":"synthetic","xor_key":5}'), \
                 patch.object(images, 'validate_aes_key', return_value=False):
                with self.assertRaises(ValueError):
                    images.load_existing_key(key, Path(directory) / 'unused.dat')
            self.assertEqual(key.read_bytes(), b'synthetic-protected-data')

    def test_valid_image_key_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'synthetic.dpapi'
            key.write_bytes(b'synthetic-protected-data')
            with patch.object(images, 'encrypted_probe', return_value=b'0' * 16), \
                 patch.object(images, 'unprotect_with_dpapi', return_value=b'{"aes_key":"synthetic","xor_key":5}'), \
                 patch.object(images, 'validate_aes_key', return_value=True):
                self.assertEqual(images.load_existing_key(key, Path(directory) / 'unused.dat'),
                                 ('synthetic', 5, 'dpapi_cache'))
            self.assertEqual(key.read_bytes(), b'synthetic-protected-data')

    def load(self, root, messages):
        path = root / 'messages.json'
        path.write_text(json.dumps({'chat': 'Synthetic project', 'messages': messages}), encoding='utf-8')
        index, title = mapper.load_message_export(path)
        self.assertEqual(title, 'Synthetic project')
        return index

    def test_same_local_id_different_shards(self):
        with tempfile.TemporaryDirectory() as directory:
            index = self.load(Path(directory), [dict(local_id=1, server_id=11, sender='First'),
                                                dict(local_id=1, server_id=22, sender='Second')])
            self.assertEqual(mapper.match_message(index, {'message_svr_id': 11})['sender'], 'First')
            self.assertEqual(mapper.match_message(index, {'message_svr_id': 22})['sender'], 'Second')

    def test_fallback_requires_unique_time_and_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = dict(local_id=1, server_id=0, create_time=100, raw_type=3)
            row = dict(message_svr_id=0, message_local_id=1, message_create_time=100, message_local_type=3)
            self.assertIsNotNone(mapper.match_message(self.load(root, [item]), row))
            self.assertIsNone(mapper.match_message(self.load(root, [item, item]), row))
            row['message_create_time'] = 99
            self.assertIsNone(mapper.match_message(self.load(root, [item]), row))

    def test_ambiguous_filename_not_arbitrarily_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / 'a.txt', Path(directory) / 'b.txt'
            a.write_bytes(b'one')
            b.write_bytes(b'two')
            self.assertIsNone(mapper.choose_file([a, b], {3}))
            self.assertEqual(mapper.choose_file([a], {3}), a)
            self.assertIsNone(mapper.choose_file([a], {4}))


if __name__ == '__main__':
    unittest.main()
