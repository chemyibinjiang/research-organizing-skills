# Group Assignment Checker

Run with Python 3.11+, no third-party dependencies. Paths are relative to this
skill directory, including when installed separately:

```powershell
python scripts/check_assignments.py assets/assignments.synthetic.json
python scripts/check_assignments.py assets/assignments.synthetic.json --final
```

The fictional example passes both commands. Exit 0 means supplied constraints
pass; 1 means findings needing review; 2 means malformed input. Output is JSON on
stdout, with no file edits or external actions.

Root `schema_version` is 1. The other required fields are:

- `rules`: integer `reviewers_per_group`, `awards_per_group`,
  `max_posters_per_group`, `max_groups_per_reviewer`. Only the awards quota can be
  zero. Set these from the organizer's approved rule, not from the example.
- `posters`: `{id, status}` records, with unique stable IDs and status `active`,
  `withdrawn` or `display_only`. Retain inactive IDs in this snapshot for validation.
- `reviewers`: `{id, conflicts}` records. `conflicts` explicitly lists poster IDs
  covered by declared conflicts. An empty list means no supplied conflicts, not
  that all real conflicts have been checked.
- `groups`: `{id, reviewer_ids, poster_ids, selected_ids?}` records. Each group
  member reviews the entire group list. IDs inside each list must be unique.

This model assigns every active poster to exactly one group. It does not represent
independent per-poster panels or weighted scores. Translate only a matching policy;
do not force a different event into this schema. The student-forum planning guidance
in the skill also needs its own event-specific scoring and eligibility checks.

Without `--final`, selections may be incomplete but cannot exceed the quota or
include ineligible/out-of-group posters. With `--final`, each group must return
exactly its quota. Human-approved exceptions require an amended rule or a documented
exception; do not hide validation findings to obtain a passing report.

The checker finds missing/duplicate coverage, missing reviewer IDs, ineligible
assignments/selections, declared conflicts, group/reviewer workload and duplicate
awards. It cannot infer undeclared relationships, scientific fit, agreement among
judges, attendance or quality of selections. Approval and communication remain
separate operational records.
