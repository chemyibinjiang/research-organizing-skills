# Research Organizing Skills

Human-led AI assistance for research coordination: reading selected WeChat
conversations, handling email, planning academic programmes and delivering event
materials with traceable decisions and handovers.

These workflows grew out of a session secretary's work at a chemistry conference
and were refactored afterwards for other projects. They are not an autonomous
conference organizer or an institution-endorsed product.

## What works now

| Component | Capability | Boundary |
| --- | --- | --- |
| [`wechat-local-reader`](skills/wechat-local-reader/SKILL.md) | Selected group/private-chat retrieval, committed snapshots, source-linked summaries, attachment mapping | Windows and a compatible local WeChat database with an existing authorized key; no sending or key recovery |
| [`email-correspondence`](skills/email-correspondence/SKILL.md) | Read Inbox/Sent, record correspondence, prepare threaded attachments, send approved messages, verify Sent | Human approval; no blind retry; local adapter is plain-text IMAP/SMTP |
| [`conference-state-handoff`](skills/conference-state-handoff/SKILL.md) | Reconcile decisions, owners, pending work and topic handoffs | Procedure and template; no automatic cross-chat synchronization |
| [`speaker-reviewer-planning`](skills/speaker-reviewer-planning/SKILL.md) | Expert shortlists, diversity accounting, reviewer matching, stable IDs and late changes | Human academic decisions; executable group-assignment checks |
| [`conference-programme-check`](skills/conference-programme-check/SKILL.md) | Chair/speaker/interview/tour conflicts and transfer buffers | Executable explicit-interval checks; no inferred traffic or availability |
| [`participant-logistics`](skills/participant-logistics/SKILL.md) | Reception, accommodation, meals, vehicles and volunteer handoffs | Procedure and blank roster; payment and booking evidence stay separate |
| [`conference-materials-release`](skills/conference-materials-release/SKILL.md) | Scripts, run sheets, slides, seating and print-only delivery | Procedure and manifest; requires document tools for authoring/rendering |
| [`conference-exception-handling`](skills/conference-exception-handling/SKILL.md) | Triage unexpected changes, assess dependencies, agree fallbacks and verify resolution | Human decision authority; incident template and fictional scenarios, not automatic recovery |
| `templates/` | Current-state, handover, contact and correspondence templates | Blank starting points, not a shared database or automated coordination engine |

The scripts are usable without an agent. `SKILL.md` files explain how an agent
should use them. Multiple topic chats are optional, not required infrastructure.
The six conference workflows were extracted after the event. Their packaged
instructions and new validators are not claimed to have run during the conference.

## Start here

1. Read [Setup](docs/SETUP.md) or [中文使用说明](docs/SETUP.zh-CN.md).
2. Install Python 3.11 and the dependencies in your own environment.
3. Run `python scripts/run_tests.py`. Tests use synthetic data and fake mail servers.
4. Preview installation with `python scripts/install_skills.py`; add `--apply`
   to copy the skills. Existing different files are never overwritten.
5. For communication tools, configure your own private account profile outside
   this repository. The conference checkers need only Python and synthetic/local JSON.

Examples of agent requests:

- "Use $wechat-local-reader to review the selected project group since yesterday.
  Summarize changed decisions and actions, with the source messages."
- "Use $email-correspondence to check this collaborator's thread and prepare a
  reply with these attachments. Do not send yet."
- "Use $speaker-reviewer-planning to match these abstracts to reviewer expertise,
  explain the proposed groups and check coverage and declared conflicts."
- "Use $conference-programme-check to check chair duties, interviews and travel
  against the approved programme. Keep unknown times explicit."
- "Use $conference-materials-release to prepare only the final print files and
  a quantity manifest, preserving the host's manual edits."
- "Use $conference-exception-handling to assess this last-minute cancellation,
  identify affected duties and propose a recovery. Do not notify anyone yet."

See the [Chinese workflow examples](docs/CONFERENCE_WORKFLOWS.zh-CN.md) for how
these skills fit together, and [offline validation](docs/VALIDATION.md) for commands.

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
