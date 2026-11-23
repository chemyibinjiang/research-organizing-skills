# Schedule Checker

Run with Python 3.11+, no third-party dependencies. Paths below are relative to
this skill directory (in the repository or an installed copy):

```powershell
python scripts/check_schedule.py assets/schedule.synthetic.json
```

The example is fictional and deliberately includes an overlap and an unknown
time, so exit status 1 is expected. Exit 0 means no issues in supplied intervals;
2 means invalid input. The script reads a file and prints JSON; it never edits it.

Root: `schema_version: 1`, nonempty `events` array. Every event has:

| Field | Meaning |
| --- | --- |
| `id` | Unique nonempty event ID |
| `start`, `end` | ISO 8601 date/time with explicit UTC offset, or `null` for unknown |
| `resources` | Nonempty unique IDs of people, groups, rooms or other exclusive resources |
| `before_minutes`, `after_minutes` | Optional nonnegative integer buffers; default 0 |

Use the same resource ID for the same person even if they have several roles.
Compare intervals as `[start - before, end + after)`: adjacent intervals without
buffers do not clash. Buffers conservatively reserve **all** resources on an event.
For different per-resource walking/setup times, create separate transition events.
For example, a speaker's walk should not also reserve the lecture room unless
that is intended. Explicitly encode shared-corridor occupancy, not just room visits.

Each overlap lists both event IDs and shared resources. A missing time is reported
as `unknown_time` and excluded from overlap comparisons; it is never called free.
Cancelled events should be kept in the private history, not this active snapshot.
Unconfirmed but proposed events can be included for conservative scenario checks.

This is an exclusive-resource interval checker, not a routing engine. It does not
infer transfer durations, traffic, capacity, meal access or attendance. Zero buffers
are a modelling choice, not evidence that no transfer time is necessary.
