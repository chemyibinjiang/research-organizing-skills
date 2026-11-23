import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/check_schedule.py'
spec = importlib.util.spec_from_file_location('schedule_checker', SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def event(ident, start='14:00', end='14:30', resources=None):
    return {'id': ident, 'start': f'2030-05-12T{start}:00+08:00',
            'end': f'2030-05-12T{end}:00+08:00', 'resources': resources or ['speaker-demo']}


def check(*events):
    return checker.check({'schema_version': 1, 'events': list(events)})


class ScheduleTests(unittest.TestCase):
    def test_shared_speaker_overlap(self):
        result = check(event('talk'), event('interview', '14:20', '14:40'))
        self.assertEqual(result['issues'][0]['resources'], ['speaker-demo'])

    def test_adjacent_is_not_overlap(self):
        self.assertEqual(check(event('a'), event('b', '14:30', '15:00'))['issues'], [])

    def test_buffer_finds_conflict(self):
        a = event('a')
        a['after_minutes'] = 5
        self.assertEqual(len(check(a, event('b', '14:32', '15:00'))['issues']), 1)

    def test_different_resources(self):
        self.assertEqual(check(event('a'), event('b', resources=['other']))['issues'], [])

    def test_shared_corridor(self):
        a = event('downstairs', resources=['group-1', 'corridor'])
        b = event('upstairs', resources=['group-2', 'corridor'])
        self.assertEqual(check(a, b)['issues'][0]['resources'], ['corridor'])

    def test_unknown_is_not_available(self):
        a = event('a')
        a['end'] = None
        result = check(a)
        self.assertEqual(result['events_with_known_intervals'], 0)
        self.assertEqual(result['issues'][0]['kind'], 'unknown_time')

    def test_offsets_compare_actual_instants(self):
        a = event('a')
        b = event('b')
        b.update(start='2030-05-12T06:20:00+00:00', end='2030-05-12T06:40:00+00:00')
        self.assertEqual(len(check(a, b)['issues']), 1)

    def test_invalid_times_and_buffers(self):
        for values in ({'start': '2030-05-12T14:00:00'}, {'end': '2030-05-12T13:00:00+08:00'},
                       {'before_minutes': -1}, {'after_minutes': True}, {'start': 42}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                a = event('a')
                a.update(values)
                check(a)

    def test_bad_resources_and_ids(self):
        with self.assertRaises(ValueError):
            check(event('a'), event('a'))
        for resources in ([], ['x', 'x'], [None]):
            with self.subTest(resources=resources), self.assertRaises(ValueError):
                a = event('a')
                a['resources'] = resources
                check(a)

    def test_invalid_documents(self):
        for data in ([], {}, {'schema_version': True, 'events': [event('a')]},
                     {'schema_version': 1, 'events': []}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                checker.check(data)

    def test_input_is_unchanged(self):
        a = event('a')
        original = copy.deepcopy(a)
        check(a)
        self.assertEqual(a, original)

    def test_cli_synthetic_and_invalid(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(ROOT / 'assets/schedule.synthetic.json')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(json.loads(result.stdout)['issues']), 2)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'invalid.json'
            path.write_text('{', encoding='utf-8')
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
