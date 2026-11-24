"""Packaging and adapter tests using temporary files and mocked credentials."""
import importlib.util
from pathlib import Path
import re
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
    def test_installer_includes_all_skills_and_assets(self):
        installer = module('installer_assets', ROOT / 'scripts/install_skills.py')
        with tempfile.TemporaryDirectory() as temp:
            actions = installer.plan(Path(temp) / 'skills')
        sources = {p.relative_to(ROOT).as_posix() for p, _ in actions}
        entrypoints = {p for p in sources if p.endswith('/SKILL.md')}
        self.assertEqual(len(entrypoints), 8)
        self.assertIn('skills/conference-programme-check/assets/schedule.synthetic.json', sources)
        self.assertIn('skills/participant-logistics/assets/logistics.template.csv', sources)
        self.assertIn('skills/conference-exception-handling/assets/incident-record.template.md', sources)
        self.assertIn('skills/conference-exception-handling/references/scenarios.md', sources)

    def test_installer_cannot_target_repository(self):
        installer = module('installer_boundary', ROOT / 'scripts/install_skills.py')
        for destination in (ROOT, ROOT / 'nested'):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                installer.plan(destination)

    def test_new_skill_links_resolve_in_standalone_folder(self):
        names = ('conference-state-handoff', 'speaker-reviewer-planning',
                 'conference-programme-check', 'participant-logistics', 'conference-materials-release',
                 'conference-exception-handling')
        for name in names:
            root = ROOT / 'skills' / name
            source = (root / 'SKILL.md').read_text(encoding='utf-8')
            self.assertIn(f'name: {name}\n', source)
            for link in re.findall(r'\]\(([^)]+)\)', source):
                with self.subTest(skill=name, link=link):
                    target = (root / link).resolve()
                    self.assertIn(root, target.parents)
                    self.assertTrue(target.is_file())

    def test_all_skill_ui_metadata_invokes_its_skill(self):
        import yaml
        for entry in (ROOT / 'skills').glob('*/SKILL.md'):
            data = yaml.safe_load((entry.parent / 'agents/openai.yaml').read_text(encoding='utf-8'))
            interface = data['interface']
            self.assertIn('$' + entry.parent.name, interface['default_prompt'])
            self.assertTrue(25 <= len(interface['short_description']) <= 64)

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
