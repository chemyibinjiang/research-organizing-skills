"""Reusable mail workflow; existing helper credentials, offline preparation, gated send."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime, getaddresses, make_msgid
import hashlib
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import re
import smtplib
import ssl
import sys
import uuid

SKILL = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def config_path():
    return Path(os.environ['LOCALAPPDATA']) / 'Codex/communication-skills/profiles.json'


def load_profile(path, name):
    profile = read_json(path)['email'][name]
    for directory in reversed(profile.get('runtime_paths', [])):
        sys.path.insert(0, directory)
    return profile


def identity(profile):
    return {key: profile[key] for key in ('username', 'imap_host', 'imap_port',
            'smtp_host', 'smtp_port', 'sent_folder', 'helper')}


def load_helper(profile):
    spec = importlib.util.spec_from_file_location('existing_mail_helper', profile['helper'])
    if spec is None or spec.loader is None:
        raise ValueError('Configured helper cannot be imported')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def credential(profile):
    helper = load_helper(profile)
    password = helper.saved_password(profile['username'])
    if not password:
        raise RuntimeError('Existing credential unavailable; no prompt or settings change attempted')
    return helper, password


def connect(profile, helper, password):
    mailbox = helper.MailBox(profile['imap_host'], profile['imap_port'],
                             ssl_context=ssl.create_default_context(), timeout=45)
    mailbox.login(profile['username'], password, initial_folder=None)
    return mailbox


def new_run(profile, kind):
    root = Path(profile['work_root']).expanduser().resolve()
    if root == SKILL or SKILL in root.parents:
        raise ValueError('Mail evidence must be outside the skill')
    run = root / kind / uuid.uuid4().hex
    run.mkdir(parents=True, exist_ok=False)
    return run


def addresses(values):
    if not isinstance(values, list):
        raise ValueError('Address fields must be lists of addr-spec strings')
    result = []
    for value in values:
        parsed = Address(addr_spec=value)
        if not parsed.username or not parsed.domain or not value.isascii() or parsed.addr_spec != value:
            raise ValueError('Use explicit ASCII addr-spec addresses, without display names')
        if value.casefold() in {v.casefold() for v in result}:
            raise ValueError('Duplicate address in recipient list')
        result.append(value)
    return result


def thread_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'<[^<>\s]+>', value):
        raise ValueError('Invalid thread Message-ID')
    return value


def prepare(profile, spec):
    allowed = {'to', 'cc', 'subject', 'body', 'attachments', 'in_reply_to', 'references', 'reply_to'}
    if set(spec) - allowed:
        raise ValueError('Unsupported message fields: ' + ', '.join(sorted(set(spec) - allowed)))
    to, cc = addresses(spec['to']), addresses(spec.get('cc', []))
    reply_to = addresses(spec.get('reply_to', []))
    if not to or {x.casefold() for x in to} & {x.casefold() for x in cc}:
        raise ValueError('Require recipients and no To/CC overlap')
    addresses([profile['username']])
    msg = EmailMessage(policy=policy.SMTP)
    msg['From'] = profile['username']
    msg['To'] = ', '.join(to)
    if cc:
        msg['Cc'] = ', '.join(cc)
    if reply_to:
        msg['Reply-To'] = ', '.join(reply_to)
    msg['Subject'] = spec['subject']
    msg['Date'] = format_datetime(datetime.now(timezone.utc))
    msg['Message-ID'] = make_msgid(domain=profile['username'].split('@')[1])
    if spec.get('in_reply_to'):
        msg['In-Reply-To'] = thread_id(spec['in_reply_to'])
    if spec.get('references'):
        msg['References'] = ' '.join(thread_id(v) for v in spec['references'])
    msg.set_content(spec['body'], charset='utf-8', cte='base64')
    attachments = []
    for filename in spec.get('attachments', []):
        path = Path(filename)
        if not path.is_absolute():
            raise ValueError('Attachments require absolute paths')
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        maintype, subtype = mime.split('/', 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
        attachments.append(dict(filename=path.name, path=str(path.resolve()), sha256=sha(data)))
    raw = msg.as_bytes()
    canonical = dict(sender=profile['username'], to=to, cc=cc, reply_to=reply_to,
                     subject=spec['subject'], body=spec['body'].replace('\r\n', '\n').rstrip('\n'),
                     in_reply_to=spec.get('in_reply_to'), references=spec.get('references', []),
                     attachments=[{k: a[k] for k in ('filename', 'sha256')} for a in attachments])
    fingerprint = sha(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode())
    job = new_run(profile, 'jobs')
    manifest = dict(prepared_at=now(), account=identity(profile), expected=canonical,
                    attachments=attachments, eml_sha256=sha(raw), fingerprint=fingerprint,
                    message_id=str(msg['Message-ID']))
    (job / 'message.eml').write_bytes(raw)
    save(job / 'manifest.json', manifest)
    (job / 'review.txt').write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding='utf-8')
    return job, manifest


def actual_addresses(msg, header):
    return [addr.casefold() for _, addr in getaddresses(msg.get_all(header, []))]


def validate(raw, manifest):
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    expected = manifest['expected']
    for header, key in [('From', 'sender'), ('To', 'to'), ('Cc', 'cc'), ('Reply-To', 'reply_to')]:
        values = [expected[key]] if key == 'sender' else expected[key]
        if actual_addresses(msg, header) != [v.casefold() for v in values]:
            raise ValueError('Message address mismatch: ' + header)
    if msg.get('Bcc') or str(msg['Subject']) != expected['subject'] or str(msg['Message-ID']) != manifest['message_id']:
        raise ValueError('Subject, Message-ID or BCC mismatch')
    if msg.get('In-Reply-To') != expected['in_reply_to']:
        raise ValueError('Reply thread mismatch')
    if str(msg.get('References', '')).split() != expected['references']:
        raise ValueError('References mismatch')
    part = msg.get_body(preferencelist=('plain',))
    if part is None or part.get_content().replace('\r\n', '\n').rstrip('\n') != expected['body']:
        raise ValueError('Body mismatch')
    actual = [{'filename': a.get_filename(), 'sha256': sha(a.get_payload(decode=True))}
              for a in msg.iter_attachments()]
    if actual != expected['attachments']:
        raise ValueError('Attachment mismatch')


def load_job(profile, job):
    job = Path(job).resolve()
    expected_root = Path(profile['work_root']).expanduser().resolve() / 'jobs'
    if expected_root not in job.parents:
        raise ValueError('Job does not belong to this account work root')
    manifest = read_json(job / 'manifest.json')
    raw = (job / 'message.eml').read_bytes()
    if manifest['account'] != identity(profile) or sha(raw) != manifest['eml_sha256']:
        raise ValueError('Account or prepared bytes changed; prepare and review again')
    validate(raw, manifest)
    return manifest, raw


def find_sent(profile, helper, password, message_id):
    mailbox = connect(profile, helper, password)
    try:
        helper.select_readonly(mailbox, profile['sent_folder'])
        status, data = mailbox.client.uid('search', None, f'(HEADER Message-ID "{thread_id(message_id)}")')
        if status != 'OK':
            raise RuntimeError('Sent search failed; sending is not safe')
        ids = data[0].split() if data and data[0] else []
        if not ids:
            return None
        uid = ids[-1].decode()
        status, fetched = mailbox.client.uid('fetch', uid, '(BODY.PEEK[])')
        parts = [part[1] for part in fetched if isinstance(part, tuple)]
        if status != 'OK' or len(parts) != 1:
            raise RuntimeError('Cannot retrieve unambiguous Sent copy')
        return uid, parts[0]
    finally:
        mailbox.logout()


def verify(profile, job, helper=None, password=None):
    job = Path(job)
    manifest, _ = load_job(profile, job)
    if helper is None:
        helper, password = credential(profile)
    found = find_sent(profile, helper, password, manifest['message_id'])
    result = dict(checked_at=now(), status='sent_copy_not_found')
    if found:
        uid, raw = found
        validate(raw, manifest)
        (job / 'verified_sent.eml').write_bytes(raw)
        result.update(status='sent_copy_verified', uid=uid, folder=profile['sent_folder'])
    save(job / 'verification.json', result)
    return result


def send(profile, job, approved_sha256, approval_ref, preflight_ref):
    job = Path(job)
    manifest, raw = load_job(profile, job)
    if approved_sha256 != sha(raw) or not approval_ref.strip():
        raise ValueError('Require the reviewed EML hash and explicit user approval reference')
    preflight = Path(preflight_ref)
    age = datetime.now(timezone.utc).timestamp() - preflight.stat().st_mtime
    if not 0 <= age <= 900:
        raise ValueError('Thread/Sent review evidence must be refreshed within 15 minutes')
    guard_dir = Path(profile['work_root']).resolve() / 'send-attempts'
    guard_dir.mkdir(parents=True, exist_ok=True)
    guard = guard_dir / (manifest['fingerprint'] + '.json')
    # Exclusive creation prevents concurrent or ambiguous automatic retries.
    with guard.open('x', encoding='utf-8') as stream:
        json.dump({'job': str(job.resolve()), 'reserved_at': now()}, stream)
    log = dict(status='preflight_started', message_id=manifest['message_id'],
               approval_ref=approval_ref, approved_sha256=approved_sha256,
               preflight_ref=str(preflight.resolve()), preflight_sha256=sha(preflight.read_bytes()))
    save(job / 'send_log.json', log)
    try:
        helper, password = credential(profile)
        if find_sent(profile, helper, password, manifest['message_id']):
            log['status'] = 'already_in_sent_no_send'
            save(job / 'send_log.json', log)
            return verify(profile, job, helper, password)
        with smtplib.SMTP_SSL(profile['smtp_host'], profile['smtp_port'],
                              context=ssl.create_default_context(), timeout=45) as smtp:
            smtp.login(profile['username'], password)
            log.update(status='attempting', attempted_at=now())
            save(job / 'send_log.json', log)
            recipients = manifest['expected']['to'] + manifest['expected']['cc']
            refused = smtp.sendmail(profile['username'], recipients, raw)
            log.update(status='partial_acceptance' if refused else 'smtp_accepted',
                       refused={k: str(v) for k, v in refused.items()}, accepted_at=now())
            save(job / 'send_log.json', log)
    except Exception as exc:
        before_dispatch = log['status'] == 'preflight_started'
        if log['status'] == 'attempting':
            log['status'] = 'outcome_uncertain'
        elif before_dispatch:
            log['status'] = 'pre_dispatch_failed'
        log['error_type'] = type(exc).__name__
        save(job / 'send_log.json', log)
        if before_dispatch:
            save(job / ('pre_dispatch_failure_' + uuid.uuid4().hex + '.json'), log)
            # Only this invocation's guard is released, before sendmail was entered.
            guard.unlink()
        raise
    try:
        result = verify(profile, job, helper, password)
    except Exception as exc:
        result = {'status': 'sent_verification_pending', 'error_type': type(exc).__name__}
        save(job / 'verification.json', result)
    return {'transport': log['status'], 'verification': result['status']}


def retrieve(profile, args):
    from imap_tools import AND, OR
    run = new_run(profile, 'reads')
    helper, password = credential(profile)
    mailbox = connect(profile, helper, password)
    records, coverage = [], []
    try:
        folders = args.folder or profile['folders']
        for folder in folders:
            helper.select_readonly(mailbox, folder)
            uidvalidity = mailbox.client.response('UIDVALIDITY')[1]
            if args.mode == 'fetch':
                criteria = AND(uid=args.uid)
                limit = 1
            else:
                terms = {'date_gte': date.fromisoformat(args.since)}
                if args.before:
                    terms['date_lt'] = date.fromisoformat(args.before)
                if args.subject:
                    terms['subject'] = args.subject
                criteria = AND(OR(from_=args.address, to=args.address, cc=args.address), **terms) if args.address else AND(**terms)
                limit = args.limit
            charset = 'US-ASCII' if str(criteria).isascii() else 'UTF-8'
            messages = list(mailbox.fetch(criteria, charset=charset, limit=limit + 1, reverse=True,
                                          mark_seen=False, headers_only=False))
            coverage.append(dict(folder=folder, truncated=len(messages) > limit,
                                 returned=min(limit, len(messages))))
            for msg in messages[:limit]:
                attachments = []
                for index, attachment in enumerate(msg.attachments):
                    item = dict(filename=attachment.filename, size=len(attachment.payload),
                                sha256=sha(attachment.payload))
                    if args.mode == 'fetch' and args.save_attachments:
                        safe = re.sub(r'[^\w.\-]', '_', attachment.filename or 'attachment')[:100]
                        target = run / f'{len(records):04d}_{index:02d}_{safe}'
                        target.write_bytes(attachment.payload)
                        item['local_path'] = str(target)
                    attachments.append(item)
                records.append(dict(account=profile['username'], folder=folder,
                    uidvalidity=[v.decode() if isinstance(v, bytes) else v for v in uidvalidity or []],
                    uid=msg.uid, date=helper.date_label(msg), sender=msg.from_,
                    to=list(msg.to), cc=list(msg.cc), subject=msg.subject,
                    message_id=msg.headers.get('message-id', []),
                    in_reply_to=msg.headers.get('in-reply-to', []),
                    references=msg.headers.get('references', []),
                    body=msg.text or helper.strip_html(msg.html), attachments=attachments))
    finally:
        mailbox.logout()
    save(run / 'correspondence.json', dict(checked_at=now(), coverage=coverage, records=records))
    return {'run': str(run), 'count': len(records), 'coverage': coverage}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['search', 'fetch', 'prepare', 'send', 'verify'])
    parser.add_argument('--config', type=Path, default=config_path())
    parser.add_argument('--profile', required=True)
    parser.add_argument('--since')
    parser.add_argument('--before')
    parser.add_argument('--subject')
    parser.add_argument('--address')
    parser.add_argument('--folder', action='append')
    parser.add_argument('--uid')
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--save-attachments', action='store_true')
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--job', type=Path)
    parser.add_argument('--approved-sha256')
    parser.add_argument('--approval-ref')
    parser.add_argument('--preflight-ref')
    args = parser.parse_args()
    profile = load_profile(args.config, args.profile)
    if args.mode == 'search' and (not args.since or not 1 <= args.limit <= 500):
        parser.error('search needs --since and --limit between 1 and 500')
    if args.mode == 'fetch' and (not args.uid or not args.folder or len(args.folder) != 1):
        parser.error('fetch needs --uid and exactly one --folder')
    if args.mode in ('search', 'fetch'):
        result = retrieve(profile, args)
    elif args.mode == 'prepare':
        if not args.spec:
            parser.error('prepare needs --spec')
        job, manifest = prepare(profile, read_json(args.spec))
        result = {'job': str(job), 'review': str(job / 'review.txt'), 'eml_sha256': manifest['eml_sha256']}
    else:
        if not args.job:
            parser.error('send/verify needs --job')
        if args.mode == 'verify':
            result = verify(profile, args.job)
        else:
            if not all((args.approved_sha256, args.approval_ref, args.preflight_ref)):
                parser.error('send requires approved hash, approval reference and fresh preflight evidence')
            result = send(profile, args.job, args.approved_sha256, args.approval_ref, args.preflight_ref)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
