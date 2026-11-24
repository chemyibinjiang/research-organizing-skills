# Setup for colleagues

## Environment

The initial supported environment is Windows with Python 3.11. WeChat decoding
uses Windows DPAPI and a compatible local database; this is not a cross-platform
WeChat connector. Email can also use an already authenticated connector instead
of the local IMAP/SMTP adapter.

From the repository directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/run_tests.py
.\.venv\Scripts\python.exe scripts/install_skills.py
.\.venv\Scripts\python.exe scripts/install_skills.py --apply
```

Do not run installation with `--apply` until you have reviewed its destination.
If different skills already exist there, reconcile your changes manually; the
installer deliberately refuses to overwrite them. Installation does not configure
accounts, obtain secrets, enable sending or grant access to colleagues' data.

## Private profile

Use `config/profiles.example.json` as a schema. Create your real profile at
`%LOCALAPPDATA%/Codex/communication-skills/profiles.json`, outside the repository.
If that file exists, merge only a new named profile; never replace existing
account settings. Both CLIs also accept `--config` for a different private path.

Replace sample paths with your own Python executable, account paths and private
work directories. All example mail addresses and hosts are deliberately non-working.
The `work` profile name is only a placeholder. Confirm that your mail provider
and organization permit this access method, then verify your real hosts and Sent
folder. A working login does not establish organizational authorization. Keep
profile names in CLI commands consistent with your file.

## Mail authentication

You can point `helper` to an existing compatible helper implementing
`saved_password`, `MailBox`, `select_readonly`, `date_label` and `strip_html`.
Do not change that helper or its saved password as part of migration.

For a new account using `adapters/imap_account.py`, provision your own approved
client/app password in the OS keyring under service `Research Organizing Skills`
and your exact email username. One interactive option, after confirming the
provider permits password-based IMAP/SMTP, is:

```powershell
.\.venv\Scripts\python.exe -m keyring set "Research Organizing Skills" "you@institution.example"
```

Enter the credential interactively, never in a prompt, command argument, JSON,
git commit or chat. OAuth-only accounts need an appropriate connector. Nothing in
the installer or tests creates, changes or retrieves real account credentials.

## WeChat prerequisites

You need your own authorized local account, a compatible `db_storage` layout and
an already provisioned DPAPI-protected database key. Image decoding needs its own
existing protected image key. This repository does not extract or recover keys.
If those prerequisites are unavailable, use an authorized UI/export route instead.
Do not point outputs into the live account tree. Read selected conversations only.

## First use

Read each installed `SKILL.md` and its relevant reference. Start with a bounded
read-only task. For email preparation, inspect the EML/review file and attachments
before approving any send. Check Inbox and Sent immediately before dispatch.

Private data remains private even when an agent is used: a local file operation
does not mean that subsequent model processing is local. Follow your institution's
rules for placing correspondence or attachments in an external AI context.
