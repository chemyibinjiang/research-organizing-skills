"""Offline tests: fake SMTP and fake mailbox, no real profiles or network."""
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mail_workflow as mail


class MailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = dict(username='sender@example.invalid', imap_host='imap.example.invalid',
            imap_port=993, smtp_host='smtp.example.invalid', smtp_port=465,
            sent_folder='Sent', helper='unused-offline-helper',
            folders=['INBOX', 'Sent'], work_root=str(self.root / 'private'))
        self.attachment = self.root / 'attachment.txt'
        self.attachment.write_text('Synthetic attachment', encoding='utf-8')
        self.spec = dict(to=['recipient@example.invalid'], cc=['copy@example.invalid'],
            subject='Unicode \u4e2d\u6587', body='Dear colleague,\n\n\u8c22\u8c22\uff01\n',
            attachments=[str(self.attachment)], in_reply_to='<parent@example.invalid>',
            references=['<parent@example.invalid>'])
        self.preflight = self.root / 'preflight.json'
        self.preflight.write_text('{"synthetic": true}', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def job(self):
        return mail.prepare(self.profile, self.spec)

    def send(self, job, manifest):
        return mail.send(self.profile, job, manifest['eml_sha256'],
                         'synthetic-user-approval', self.preflight)

    def test_offline_prepare_thread_and_unicode(self):
        with patch.object(mail, 'credential', side_effect=AssertionError('No credentials in prepare')):
            job, manifest = self.job()
        raw = (job / 'message.eml').read_bytes()
        mail.validate(raw, manifest)
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(msg['In-Reply-To'], '<parent@example.invalid>')
        self.assertIn('\u8c22\u8c22', msg.get_body(('plain',)).get_content())
        self.assertEqual(list(msg.iter_attachments())[0].get_payload(decode=True), self.attachment.read_bytes())

    def test_cli_prepare_uses_only_synthetic_profile(self):
        config = self.root / 'profiles.json'
        spec = self.root / 'message.json'
        mail.save(config, {'email': {'synthetic': self.profile}})
        mail.save(spec, self.spec)
        result = subprocess.run([sys.executable, str(Path(mail.__file__)), 'prepare',
            '--config', str(config), '--profile', 'synthetic', '--spec', str(spec)],
            capture_output=True, text=True, encoding='utf-8', check=True, timeout=15)
        prepared = mail.json.loads(result.stdout)
        manifest, _ = mail.load_job(self.profile, prepared['job'])
        self.assertEqual(prepared['eml_sha256'], manifest['eml_sha256'])
        self.assertFalse((Path(prepared['job']) / 'send_log.json').exists())

    def test_address_header_injection_rejected(self):
        self.spec['to'] = ['person@example.invalid\r\nBcc: bad@example.invalid']
        with self.assertRaises(ValueError):
            self.job()

    def test_unknown_field_not_silently_dropped(self):
        self.spec['bcc'] = ['private@example.invalid']
        with self.assertRaises(ValueError):
            self.job()

    def test_tampered_eml_rejected(self):
        job, _ = self.job()
        with (job / 'message.eml').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(ValueError):
            mail.load_job(self.profile, job)

    def test_changed_original_attachment_does_not_change_prepared_bytes(self):
        job, manifest = self.job()
        self.attachment.write_text('Later edit', encoding='utf-8')
        _, raw = mail.load_job(self.profile, job)
        mail.validate(raw, manifest)
        self.assertNotEqual(manifest['attachments'][0]['sha256'], mail.sha(self.attachment.read_bytes()))

    def test_wrong_approval_hash_blocks_before_credential(self):
        job, _ = self.job()
        with patch.object(mail, 'credential', side_effect=AssertionError('Must not access credentials')):
            with self.assertRaises(ValueError):
                mail.send(self.profile, job, 'wrong', 'approval', self.preflight)

    def test_stale_preflight_blocks_send(self):
        job, manifest = self.job()
        os.utime(self.preflight, (1, 1))
        with self.assertRaises(ValueError):
            self.send(job, manifest)

    def test_sent_copy_validation_detects_changed_cc_and_attachments(self):
        job, manifest = self.job()
        raw = (job / 'message.eml').read_bytes()
        changed = raw.replace(b'copy@example.invalid', b'other@example.invalid')
        with self.assertRaises(ValueError):
            mail.validate(changed, manifest)

    def test_sent_copy_validation_detects_changed_attachment(self):
        job, manifest = self.job()
        msg = BytesParser(policy=policy.default).parsebytes((job / 'message.eml').read_bytes())
        attachment = list(msg.iter_attachments())[0]
        attachment.set_payload('Q2hhbmdlZA==')
        with self.assertRaises(ValueError):
            mail.validate(msg.as_bytes(), manifest)

    def test_timeout_blocks_retry_even_in_new_job(self):
        job, manifest = self.job()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.sendmail.side_effect = TimeoutError('synthetic timeout')
        with patch.object(mail, 'credential', return_value=(object(), 'synthetic')), \
             patch.object(mail, 'find_sent', return_value=None), \
             patch.object(mail.smtplib, 'SMTP_SSL', return_value=smtp):
            with self.assertRaises(TimeoutError):
                self.send(job, manifest)
            self.assertEqual(mail.read_json(job / 'send_log.json')['status'], 'outcome_uncertain')
            another, another_manifest = self.job()
            self.assertEqual(manifest['fingerprint'], another_manifest['fingerprint'])
            with self.assertRaises(FileExistsError):
                self.send(another, another_manifest)
            self.assertEqual(smtp.sendmail.call_count, 1)

    def test_proven_predispatch_failures_release_only_own_guard(self):
        job, manifest = self.job()
        guard = Path(self.profile['work_root']) / 'send-attempts' / (manifest['fingerprint'] + '.json')
        with patch.object(mail, 'credential', side_effect=RuntimeError('synthetic missing credential')), \
             patch.object(mail.smtplib, 'SMTP_SSL') as no_smtp:
            with self.assertRaises(RuntimeError):
                self.send(job, manifest)
            no_smtp.assert_not_called()
        self.assertFalse(guard.exists())
        self.assertEqual(mail.read_json(job / 'send_log.json')['status'], 'pre_dispatch_failed')
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.login.side_effect = RuntimeError('synthetic login failure')
        with patch.object(mail, 'credential', return_value=(object(), 'synthetic')), \
             patch.object(mail, 'find_sent', return_value=None), \
             patch.object(mail.smtplib, 'SMTP_SSL', return_value=smtp):
            with self.assertRaises(RuntimeError):
                self.send(job, manifest)
            smtp.sendmail.assert_not_called()
            self.assertFalse(guard.exists())
            smtp.login.side_effect = None
            smtp.sendmail.return_value = {}
            with patch.object(mail, 'verify', return_value={'status': 'sent_copy_verified'}):
                result = self.send(job, manifest)
        self.assertEqual(result['transport'], 'smtp_accepted')
        self.assertTrue(guard.exists())
        self.assertEqual(smtp.sendmail.call_count, 1)

    def test_partial_acceptance_retained(self):
        job, manifest = self.job()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.sendmail.return_value = {'copy@example.invalid': (550, b'rejected')}
        with patch.object(mail, 'credential', return_value=(object(), 'synthetic')), \
             patch.object(mail, 'find_sent', return_value=None), \
             patch.object(mail, 'verify', return_value={'status': 'sent_copy_verified'}), \
             patch.object(mail.smtplib, 'SMTP_SSL', return_value=smtp):
            result = self.send(job, manifest)
        self.assertEqual(result['transport'], 'partial_acceptance')
        self.assertEqual(mail.read_json(job / 'send_log.json')['status'], 'partial_acceptance')

    def test_sent_search_failure_is_closed(self):
        job, manifest = self.job()
        with patch.object(mail, 'credential', return_value=(object(), 'synthetic')), \
             patch.object(mail, 'find_sent', side_effect=RuntimeError('offline')), \
             patch.object(mail.smtplib, 'SMTP_SSL') as smtp:
            with self.assertRaises(RuntimeError):
                self.send(job, manifest)
            smtp.assert_not_called()

    def test_existing_sent_message_is_not_resent(self):
        job, manifest = self.job()
        raw = (job / 'message.eml').read_bytes()
        with patch.object(mail, 'credential', return_value=(object(), 'synthetic')), \
             patch.object(mail, 'find_sent', return_value=('123', raw)), \
             patch.object(mail.smtplib, 'SMTP_SSL') as smtp:
            result = self.send(job, manifest)
        smtp.assert_not_called()
        self.assertEqual(result['status'], 'sent_copy_verified')

    def test_read_only_search_and_truncation(self):
        message = SimpleNamespace(uid='1', date=datetime.now(timezone.utc), from_='person@example.invalid',
            to=['sender@example.invalid'], cc=[], subject='Project', headers={}, text='Synthetic', html='', attachments=[])
        mailbox = MagicMock()
        mailbox.client.response.return_value = ('UIDVALIDITY', [b'5'])
        mailbox.fetch.return_value = [message, message]
        helper = SimpleNamespace(select_readonly=MagicMock(), date_label=lambda m: m.date.isoformat(), strip_html=lambda h: h)
        args = SimpleNamespace(mode='search', folder=['INBOX'], since='2026-01-01', before=None,
                               subject='\u9879\u76ee', address='person@example.invalid', limit=1)
        with patch.object(mail, 'credential', return_value=(helper, 'synthetic')), \
             patch.object(mail, 'connect', return_value=mailbox):
            result = mail.retrieve(self.profile, args)
        helper.select_readonly.assert_called_once_with(mailbox, 'INBOX')
        self.assertFalse(mailbox.fetch.call_args.kwargs['mark_seen'])
        self.assertEqual(mailbox.fetch.call_args.kwargs['charset'], 'UTF-8')
        self.assertTrue(result['coverage'][0]['truncated'])
        self.assertEqual(result['count'], 1)


if __name__ == '__main__':
    unittest.main()
