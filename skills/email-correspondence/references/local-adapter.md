# Existing Helper Adapter

Private configuration: `%LOCALAPPDATA%/Codex/communication-skills/profiles.json`.
The `email` profile references the existing helper and saved credential interface.
It contains no password. Do not run the original helper's credential-store/delete
commands. The adapter calls its existing `saved_password`, `MailBox` and
`select_readonly` interfaces; it does not modify that helper.

Use the configured Python executable. `work` is the sample profile name, not an
account or an authorization grant; match it to your own approved private profile:

```powershell
$cfg = Get-Content -LiteralPath "$env:LOCALAPPDATA/Codex/communication-skills/profiles.json" -Encoding UTF8 | ConvertFrom-Json
$py = $cfg.email.work.python
$tool = "$env:USERPROFILE/.codex/skills/email-correspondence/scripts/mail_workflow.py"
& $py $tool search --profile work --since '<YYYY-MM-DD>' --address '<selected-address>'
& $py $tool fetch --profile work --folder 'INBOX' --uid '<selected-uid>'
& $py $tool prepare --profile work --spec '<private-path/message.json>'
```

Search accepts `--before`, `--subject`, `--folder` (repeatable) and `--limit`.
`fetch --save-attachments` writes the selected message's attachments to its private
run directory. Attachment availability is not a claim that their contents were read.
JSON output includes original header times and timezone-aware check timestamps.
An IMAP date filter follows server date semantics; inspect timestamps for an exact
hour boundary. The default folders come from the profile.

Message specification (no default signature or project wording):

```json
{
  "to": ["person@example.invalid"],
  "cc": [],
  "subject": "Subject approved for this project",
  "body": "Full message, including the intended signature.\n",
  "attachments": [],
  "in_reply_to": null,
  "references": [],
  "reply_to": []
}
```

Attachment entries are absolute local path strings. `in_reply_to` and `references`
must be copied from the actual parent message when replying. No BCC or HTML is
supported by this small adapter; use an appropriate connector for those cases.

`prepare` is offline and outputs a job path, review file, manifest and EML hash.
Read the full review file. After explicit user approval AND a fresh thread/Sent
check, send the reviewed bytes:

```powershell
& $py $tool send --profile work --job '<job-path>' --approved-sha256 '<reviewed-eml-hash>' --approval-ref '<actual-user-message-reference>' --preflight-ref '<fresh-correspondence-evidence-path>'
& $py $tool verify --profile work --job '<job-path>'
```

Preflight evidence must be a local file checked within 15 minutes; its semantic
relevance still requires the agent's review. The adapter also checks the exact
Message-ID in Sent before SMTP. Content fingerprints under the account work root
block repeated attempts across jobs. An attempted/uncertain/partially accepted send
is never automatically retried. Do not delete the guard or change content just to
bypass it. An intentional resend needs a new reviewed decision and reconciliation.
An exception before `sendmail` is entered is recorded as `pre_dispatch_failed`;
only that invocation's guard is released, so the same reviewed job can be tried
after the cause is resolved and preflight is refreshed. A crash or any failure
after dispatch begins retains the guard. Never manually clear an uncertain guard.

If Sent is temporarily unavailable after acceptance, use `verify`, not `send`.
Verification never appends a synthetic Sent copy. No receipt acknowledgement or
read receipt is inferred. Errors and refusals remain in the private job log.

To configure another compatible account, add a distinct profile with username,
IMAP/SMTP TLS hosts/ports, Sent folder, helper path and work root. Verify account
authorization, provider/organizational requirements and saved-credential support
first. Do not reuse credentials across unrelated accounts. OAuth-only mail should
use an authenticated connector.
