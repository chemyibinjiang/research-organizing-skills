# Research Organizing Skills

Human-led AI assistance for research coordination: reading selected WeChat
conversations, handling email, and keeping decisions and handovers traceable.

These workflows grew out of a session secretary's work at a chemistry conference
and were refactored afterwards for other projects. They are not an autonomous
conference organizer or an institution-endorsed product.

## What works now

| Component | Capability | Boundary |
| --- | --- | --- |
| `wechat-local-reader` | Selected group/private-chat retrieval, committed snapshots, source-linked summaries, attachment mapping | Windows and a compatible local WeChat database with an existing authorized key; no sending or key recovery |
| `email-correspondence` | Read Inbox/Sent, record correspondence, prepare threaded attachments, send approved messages, verify Sent | Human approval; no blind retry; local adapter is plain-text IMAP/SMTP |
| `templates/` | Current-state, handover, contact and correspondence templates | Blank starting points, not a shared database or automated coordination engine |

The scripts are usable without an agent. `SKILL.md` files explain how an agent
should use them. Multiple topic chats are optional, not required infrastructure.

## Start here

1. Read [Setup](docs/SETUP.md) or [中文使用说明](docs/SETUP.zh-CN.md).
2. Install Python 3.11 and the dependencies in your own environment.
3. Run `python scripts/run_tests.py`. Tests use synthetic data and fake mail servers.
4. Preview installation with `python scripts/install_skills.py`; add `--apply`
   to copy the skills. Existing different files are never overwritten.
5. Configure your own private account profile outside this repository.

Examples of agent requests:

- "Use $wechat-local-reader to review the selected project group since yesterday.
  Summarize changed decisions and actions, with the source messages."
- "Use $email-correspondence to check this collaborator's thread and prepare a
  reply with these attachments. Do not send yet."

## Safety and limitations

- Reading is not permission to send. Review recipients, text and attachments first.
- An accepted send, a verified Sent copy, a reply and completed work are different states.
- Quoted old messages are not new decisions. A generated file is not proof of delivery.
- This repository contains no real chat exports, rosters, private emails or credentials.
- Keep account configuration and working evidence outside the repository, even if private.
- Live provider compatibility, complete WeChat synchronization and on-site outcomes
  are not established by the offline tests.
- The generic mail adapter requires each user to configure an authorized account.
  Confirm provider and organizational permission before connecting.

See [Validation and provenance](docs/VALIDATION.md) and [Data boundaries](docs/DATA_BOUNDARIES.md).

## Sharing and license

This is initially a private collaboration repository. Colleagues need repository
access from its owner. No open-source license has been selected; do not describe
it as open source or assume permission for public redistribution. Contributors
should agree code ownership and licensing before a public release.

The proposed article and underlying conference evidence are not part of this repository.
