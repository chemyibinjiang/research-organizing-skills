import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/check_assignments.py'
spec = importlib.util.spec_from_file_location('assignment_checker', SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def fixture():
    return json.loads((ROOT / 'assets/assignments.synthetic.json').read_text(encoding='utf-8'))


def kinds(data, final=False):
    return {x['kind'] for x in checker.check(data, final)['issues']}


class AssignmentTests(unittest.TestCase):
    def test_synthetic_valid_and_inactive_ids_retained(self):
        result = checker.check(fixture(), final=True)
        self.assertEqual(result['issues'], [])
        self.assertEqual((result['poster_slots'], result['active_posters']), (4, 2))

    def test_missing_coverage(self):
        data = fixture()
        data['groups'][0]['poster_ids'].remove('DEMO-P1')
        self.assertIn('active_coverage', kinds(data))

    def test_duplicate_group_coverage_and_award(self):
        data = fixture()
        second = copy.deepcopy(data['groups'][0])
        second['id'] = 'DEMO-G2'
        data['groups'].append(second)
        self.assertTrue({'active_coverage', 'duplicate_award', 'reviewer_workload'} <= kinds(data))

    def test_declared_conflict(self):
        data = fixture()
        data['reviewers'][0]['conflicts'] = ['DEMO-P1']
        self.assertIn('declared_conflict', kinds(data))

    def test_inactive_assignment_and_selection(self):
        for ident in ('DEMO-P3', 'DEMO-P4'):
            with self.subTest(ident=ident):
                data = fixture()
                data['groups'][0]['poster_ids'].append(ident)
                data['groups'][0]['selected_ids'] = [ident]
                self.assertTrue({'ineligible_assignment', 'ineligible_selection'} <= kinds(data))

    def test_unknown_ids(self):
        data = fixture()
        data['groups'][0]['reviewer_ids'][0] = 'unknown'
        data['groups'][0]['poster_ids'].append('unknown')
        self.assertTrue({'unknown_reviewer', 'unknown_poster'} <= kinds(data))

    def test_outside_selection(self):
        data = fixture()
        data['groups'][0]['selected_ids'] = ['DEMO-P3']
        self.assertIn('selection_outside_group', kinds(data))

    def test_final_requires_quota(self):
        data = fixture()
        data['groups'][0].pop('selected_ids')
        self.assertEqual(kinds(data), set())
        self.assertIn('award_count', kinds(data, final=True))

    def test_excess_selection_rejected_in_draft(self):
        data = fixture()
        data['groups'][0]['selected_ids'] = ['DEMO-P1', 'DEMO-P2']
        self.assertIn('award_count', kinds(data))

    def test_group_size_and_reviewer_count(self):
        data = fixture()
        data['rules']['max_posters_per_group'] = 1
        data['groups'][0]['reviewer_ids'].pop()
        self.assertTrue({'group_size', 'reviewer_count'} <= kinds(data))

    def test_duplicate_member_not_counted_twice(self):
        data = fixture()
        data['groups'][0]['reviewer_ids'] = ['DEMO-R1', 'DEMO-R1']
        with self.assertRaises(ValueError):
            checker.check(data)

    def test_invalid_rules_status_and_empty_input(self):
        for key, value in (('awards_per_group', -1), ('reviewers_per_group', True),
                           ('max_groups_per_reviewer', 0)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                data = fixture()
                data['rules'][key] = value
                checker.check(data)
        data = fixture()
        data['posters'][0]['status'] = 'maybe'
        with self.assertRaises(ValueError):
            checker.check(data)
        with self.assertRaises(ValueError):
            checker.check({})

    def test_input_is_unchanged(self):
        data = fixture()
        original = copy.deepcopy(data)
        checker.check(data)
        self.assertEqual(data, original)

    def test_cli(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(ROOT / 'assets/assignments.synthetic.json'), '--final'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['issues'], [])


if __name__ == '__main__':
    unittest.main()
