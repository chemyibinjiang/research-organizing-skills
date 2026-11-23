# Validation and provenance

The initial release contains post-conference refactorings of working local helpers,
not a reconstruction claiming these exact wrappers ran throughout the event.

Run `python scripts/run_tests.py` to reproduce the offline suites. Fixtures are
synthetic; SMTP, mailbox access and key validation are mocked where appropriate.
The runner discovers each skill's tests plus repository packaging tests.

| Suite | Coverage |
| --- | --- |
| WeChat and attachments | 14 cases retained from the initial package |
| Email | 16 cases retained from the initial package |
| Programme checker | 12 cases: overlaps, adjacency, buffers, shared corridor, unknown times, offsets, malformed inputs and CLI |
| Group assignment checker | 14 cases: coverage, withdrawals, display-only entries, declared conflicts, workload, selections and CLI |
| Packaging and adapter | Installer preview/non-overwrite, all seven skills and their assets, linked references and adapter mocks |

Checks include committed-WAL selection, cross-shard ordering and identity,
quoted/forwarded provenance, missing image-key refusal, immutable attachments,
approval/preflight checks, ambiguous-send retry blocking, proven pre-dispatch
failure recovery, and refusal to overwrite existing colleague edits.

The five conference skills added after the event are reusable procedural guidance,
not retrospective proof of an autonomous event-management system. The two new
validators operate on explicitly supplied constraints; their tests do not evaluate
semantic extraction, expert quality, unreported conflicts or real-world execution.
State/handoff, logistics and materials instructions have templates but no automated
end-to-end integration test. Document rendering uses the operator's available tools.

Standalone examples, from the repository root:

```powershell
python skills/conference-programme-check/scripts/check_schedule.py skills/conference-programme-check/assets/schedule.synthetic.json
python skills/speaker-reviewer-planning/scripts/check_assignments.py skills/speaker-reviewer-planning/assets/assignments.synthetic.json --final
```

The schedule example intentionally exits 1 with an overlap and an unknown time.
The assignment example exits 0. Neither example connects to external services.

The tests do not establish live compatibility for every WeChat version or provider,
full historical synchronization, external delivery, participant satisfaction, human
time saved, or conference-wide error rates. Encrypted live-database integration,
media variants and provider behavior need authorized environment-specific checks.

AI assisted development and documentation. Human operators remain responsible for
authorization, factual decisions and external communication. The scientific quality
of talks/posters and award decisions is outside these operational skills.
