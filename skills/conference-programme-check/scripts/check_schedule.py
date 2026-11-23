"""Read-only checks of explicit exclusive-resource intervals; JSON in and out."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path


def timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or 'T' not in value:
        raise ValueError('Times require ISO 8601 dates, T and timezone offsets')
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('Times must include timezone offsets')
    return result


def minutes(value):
    if type(value) is not int or not 0 <= value <= 10080:
        raise ValueError('Buffers must be integer minutes between 0 and 10080')
    return timedelta(minutes=value)


def check(document):
    if not isinstance(document, dict) or type(document.get('schema_version')) is not int or document['schema_version'] != 1:
        raise ValueError('Expected schema_version 1')
    events = document.get('events')
    if not isinstance(events, list) or not events:
        raise ValueError('events must be a nonempty list')
    parsed, issues, seen = [], [], set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('Every event must be an object')
        ident = event.get('id')
        if not isinstance(ident, str) or not ident.strip() or ident in seen:
            raise ValueError('Event IDs must be unique nonempty strings')
        seen.add(ident)
        resources = event.get('resources')
        if not isinstance(resources, list) or not resources or any(
                not isinstance(r, str) or not r.strip() for r in resources):
            raise ValueError(f'{ident}: resources must be nonempty string IDs')
        if len(resources) != len(set(resources)):
            raise ValueError(f'{ident}: duplicate resources')
        if 'start' not in event or 'end' not in event:
            raise ValueError(f'{ident}: supply start/end, using null for unknown')
        start, end = timestamp(event['start']), timestamp(event['end'])
        before = minutes(event.get('before_minutes', 0))
        after = minutes(event.get('after_minutes', 0))
        if start is None or end is None:
            issues.append({'kind': 'unknown_time', 'event_ids': [ident]})
            continue
        if end <= start:
            raise ValueError(f'{ident}: end must be after start')
        parsed.append((ident, start - before, end + after, set(resources)))

    for i, (ident, start, end, resources) in enumerate(parsed):
        for other, other_start, other_end, other_resources in parsed[i + 1:]:
            shared = resources & other_resources
            if shared and start < other_end and other_start < end:
                issues.append({'kind': 'overlap', 'event_ids': [ident, other],
                               'resources': sorted(shared),
                               'start': max(start, other_start).isoformat(),
                               'end': min(end, other_end).isoformat()})
    return {'status': 'needs_review' if issues else 'no_conflicts_in_supplied_intervals',
            'events_total': len(events), 'events_with_known_intervals': len(parsed),
            'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    try:
        report = check(json.loads(args.input.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, OverflowError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
