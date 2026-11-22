"""Packaging and adapter tests using temporary files and mocked credentials."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class PackagingTests(unittest.TestCase):
    def test_installer_preview_does_not_write(self):
        installer = module('installer', ROOT / 'scripts/install_skills.py')
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'skills'
            self.assertGreater(len(installer.plan(destination)), 0)
            self.assertFalse(destination.exists())

    def test_installer_rejects_overwrite(self):
        installer = module('installer', ROOT / 'scripts/install_skills.py')
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'skills'
            target = destination / 'wechat-local-reader/SKILL.md'
            target.parent.mkdir(parents=True)
            target.write_text('Existing colleague edits', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                installer.plan(destination)
            self.assertEqual(target.read_text(encoding='utf-8'), 'Existing colleague edits')

    def test_adapter_only_reads_keyring(self):
        adapter = module('adapter', ROOT / 'adapters/imap_account.py')
        with patch.object(adapter.keyring, 'get_password', return_value='synthetic') as getter, \
             patch.object(adapter.keyring, 'set_password') as setter:
            self.assertEqual(adapter.saved_password('someone@example.invalid'), 'synthetic')
        getter.assert_called_once_with(adapter.SERVICE, 'someone@example.invalid')
        setter.assert_not_called()

    def test_adapter_readonly_folder(self):
        adapter = module('adapter', ROOT / 'adapters/imap_account.py')
        mailbox = SimpleNamespace(folder=SimpleNamespace(set=Mock()))
        adapter.select_readonly(mailbox, 'INBOX')
        mailbox.folder.set.assert_called_once_with('INBOX', readonly=True)


if __name__ == '__main__':
    unittest.main()
