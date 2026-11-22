# Validation and provenance

The initial release contains post-conference refactorings of working local helpers,
not a reconstruction claiming these exact wrappers ran throughout the event.

Offline suites cover 14 WeChat/attachment cases, 16 mail cases and 4 packaging/adapter
cases. Run `python scripts/run_tests.py` to reproduce them. Fixtures are synthetic;
SMTP, mailbox access and key validation are mocked where appropriate.

Checks include committed-WAL selection, cross-shard ordering and identity,
quoted/forwarded provenance, missing image-key refusal, immutable attachments,
approval/preflight checks, ambiguous-send retry blocking, proven pre-dispatch
failure recovery, and refusal to overwrite existing colleague edits.

The tests do not establish live compatibility for every WeChat version or provider,
full historical synchronization, external delivery, participant satisfaction, human
time saved, or conference-wide error rates. Encrypted live-database integration,
media variants and provider behavior need authorized environment-specific checks.

AI assisted development and documentation. Human operators remain responsible for
authorization, factual decisions and external communication. The scientific quality
of talks/posters and award decisions is outside these operational skills.
