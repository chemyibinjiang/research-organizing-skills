"""Validate group judging coverage and declared constraints; never select winners."""
import argparse
from collections import Counter
import json
from pathlib import Path


def ids(value, label):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f'{label}: expected a list of nonempty string IDs')
    if len(value) != len(set(value)):
        raise ValueError(f'{label}: duplicate IDs')
    return value


def records(value, label):
    if not isinstance(value, list):
        raise ValueError(f'{label}: expected an array')
    result = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f'{label}: expected objects')
        ident = item.get('id')
        if not isinstance(ident, str) or not ident.strip() or ident in result:
            raise ValueError(f'{label}: IDs must be unique nonempty strings')
        result[ident] = item
    return result


def check(document, final=False):
    if not isinstance(document, dict) or type(document.get('schema_version')) is not int or document['schema_version'] != 1:
        raise ValueError('Expected schema_version 1')
    rules = document.get('rules')
    if not isinstance(rules, dict):
        raise ValueError('rules must be an object')
    for key in ('reviewers_per_group', 'awards_per_group', 'max_posters_per_group', 'max_groups_per_reviewer'):
        value = rules.get(key)
        minimum = 0 if key == 'awards_per_group' else 1
        if type(value) is not int or value < minimum:
            raise ValueError(f'{key}: expected an integer >= {minimum}')
    if rules['awards_per_group'] > rules['max_posters_per_group']:
        raise ValueError('awards_per_group exceeds max_posters_per_group')
    posters = records(document.get('posters'), 'posters')
    reviewers = records(document.get('reviewers'), 'reviewers')
    groups = records(document.get('groups'), 'groups')
    if not posters or not reviewers or not groups:
        raise ValueError('Supply nonempty posters, reviewers and groups')
    for ident, poster in posters.items():
        if poster.get('status') not in ('active', 'withdrawn', 'display_only'):
            raise ValueError(f'{ident}: invalid poster status')
    for ident, reviewer in reviewers.items():
        conflicts = ids(reviewer.get('conflicts'), f'{ident}.conflicts')
        if set(conflicts) - posters.keys():
            raise ValueError(f'{ident}: declared conflicts reference unknown posters')

    issues, coverage, workload, selected_all = [], Counter(), Counter(), Counter()

    def issue(kind, **detail):
        issues.append({'kind': kind, **detail})

    for group_id, group in groups.items():
        members = ids(group.get('reviewer_ids'), f'{group_id}.reviewer_ids')
        assigned = ids(group.get('poster_ids'), f'{group_id}.poster_ids')
        selected = ids(group.get('selected_ids', []), f'{group_id}.selected_ids')
        coverage.update(assigned)
        workload.update(members)
        selected_all.update(selected)
        if len(members) != rules['reviewers_per_group']:
            issue('reviewer_count', group_id=group_id, actual=len(members), expected=rules['reviewers_per_group'])
        if not assigned or len(assigned) > rules['max_posters_per_group']:
            issue('group_size', group_id=group_id, actual=len(assigned), maximum=rules['max_posters_per_group'])
        for poster_id in assigned:
            if poster_id not in posters:
                issue('unknown_poster', group_id=group_id, poster_id=poster_id)
            elif posters[poster_id]['status'] != 'active':
                issue('ineligible_assignment', group_id=group_id, poster_id=poster_id, status=posters[poster_id]['status'])
        for reviewer_id in members:
            if reviewer_id not in reviewers:
                issue('unknown_reviewer', group_id=group_id, reviewer_id=reviewer_id)
                continue
            for poster_id in sorted(set(reviewers[reviewer_id]['conflicts']) & set(assigned)):
                issue('declared_conflict', group_id=group_id, reviewer_id=reviewer_id, poster_id=poster_id)
        if (final and len(selected) != rules['awards_per_group']) or len(selected) > rules['awards_per_group']:
            issue('award_count', group_id=group_id, actual=len(selected), expected=rules['awards_per_group'])
        for poster_id in selected:
            if poster_id not in assigned:
                issue('selection_outside_group', group_id=group_id, poster_id=poster_id)
            if poster_id not in posters or posters[poster_id]['status'] != 'active':
                issue('ineligible_selection', group_id=group_id, poster_id=poster_id)

    for poster_id, poster in posters.items():
        if poster['status'] == 'active' and coverage[poster_id] != 1:
            issue('active_coverage', poster_id=poster_id, actual=coverage[poster_id], expected=1)
    for reviewer_id, count in sorted(workload.items()):
        if count > rules['max_groups_per_reviewer']:
            issue('reviewer_workload', reviewer_id=reviewer_id, actual=count, maximum=rules['max_groups_per_reviewer'])
    for poster_id, count in sorted(selected_all.items()):
        if count > 1:
            issue('duplicate_award', poster_id=poster_id, actual=count)
    return {'status': 'needs_review' if issues else 'passes_supplied_constraints',
            'final_selection_check': final, 'poster_slots': len(posters),
            'active_posters': sum(p['status'] == 'active' for p in posters.values()),
            'groups': len(groups), 'reviewer_group_counts': dict(sorted(workload.items())),
            'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--final', action='store_true', help='Require each group to return its exact award quota')
    args = parser.parse_args()
    try:
        report = check(json.loads(args.input.read_text(encoding='utf-8-sig')), final=args.final)
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
