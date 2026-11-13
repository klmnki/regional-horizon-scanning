import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import scanner


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.config = scanner.configuration()
        self.run = scanner.read_json(scanner.ROOT / 'examples/run.json')

    def test_fictional_demo_has_all_eight_lanes(self):
        self.assertEqual(8, len(self.run['coverage']))
        self.assertEqual([], scanner.validate(self.run, self.config))

    def test_missing_lane_cannot_be_claimed_complete(self):
        self.run['coverage'].pop()
        self.assertIn('Coverage must contain exactly one row for every configured lane', scanner.validate(self.run, self.config))

    def test_empty_and_failed_are_distinct(self):
        row = self.run['coverage'][0]
        row['Status'] = 'Failed'
        row['Gaps / access failures'] = ''
        self.assertTrue(any('needs a reason' in x for x in scanner.validate(self.run, self.config)))
        row['Gaps / access failures'] = 'Search service unavailable'
        self.assertEqual([], scanner.validate(self.run, self.config))

    def test_no_qualifying_cannot_hide_selected_records(self):
        self.run['coverage'][6]['Status'] = 'No qualifying items'
        self.assertTrue(any('cannot have selected' in x for x in scanner.validate(self.run, self.config)))

    def test_untraceable_evidence_is_excluded(self):
        fields = self.run['signals'][0]['fields']
        score = json.loads(fields['Score breakdown'])
        score['evidence'] = 0
        fields['Score breakdown'] = json.dumps(score)
        fields['Score /10'] -= 1
        self.assertTrue(any('ineligible' in x for x in scanner.validate(self.run, self.config)))

    def test_future_publication_is_rejected(self):
        self.run['signals'][0]['fields']['Publication date'] = '2026-11-14'
        self.assertTrue(any('future-dated' in x for x in scanner.validate(self.run, self.config)))

    def test_global_research_needs_transfer_test(self):
        self.run['products'][0]['fields']['Transfer test for territories'] = ''
        self.assertTrue(any('Transfer test' in x for x in scanner.validate(self.run, self.config)))

    def test_counts_and_ids_must_match_saved_evidence(self):
        self.run['coverage'][6]['Selected signals'] = 2
        self.run['coverage'][6]['Record IDs'] = ''
        errors = scanner.validate(self.run, self.config)
        self.assertTrue(any('count mismatch' in x for x in errors))
        self.assertTrue(any('IDs do not match' in x for x in errors))

    def test_duplicate_event_is_rejected_even_with_another_id(self):
        duplicate = copy.deepcopy(self.run['signals'][0])
        duplicate['fields']['Signal ID'] = 'SIG-20261113-ECA-02'
        self.run['signals'].append(duplicate)
        self.assertTrue(any('duplicate underlying' in x for x in scanner.validate(self.run, self.config)))

    def test_fictional_fixture_cannot_masquerade_as_real(self):
        self.run['example'] = False
        self.assertTrue(any('fictional URL' in x for x in scanner.validate(self.run, self.config)))

    def test_unknown_dates_are_permitted(self):
        self.run['signals'][0]['fields']['Publication date'] = ''
        self.assertEqual([], scanner.validate(self.run, self.config))

    def test_repeated_archive_is_idempotent_and_changes_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(scanner.archive(self.run, self.config, tmp).startswith('Archived'))
            self.assertTrue(scanner.archive(self.run, self.config, tmp).startswith('Unchanged'))
            self.run['signals'][0]['fields']['Headline'] = 'Changed text'
            with self.assertRaisesRegex(ValueError, 'different content'):
                scanner.archive(self.run, self.config, tmp)
            with closing(sqlite3.connect(Path(tmp) / 'archive.sqlite3')) as db:
                self.assertEqual(1, db.execute('SELECT COUNT(*) FROM runs').fetchone()[0])

    def test_cross_day_duplicate_rolls_back_entire_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner.archive(self.run, self.config, tmp)
            later = json.loads(json.dumps(self.run).replace('2026-11-13', '2026-11-14').replace('20261113', '20261114'))
            with self.assertRaisesRegex(ValueError, 'Duplicate ID or canonical'):
                scanner.archive(later, self.config, tmp)
            with closing(sqlite3.connect(Path(tmp) / 'archive.sqlite3')) as db:
                self.assertEqual(1, db.execute('SELECT COUNT(*) FROM runs').fetchone()[0])
                self.assertEqual(2, db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0])

    def test_csv_formula_is_neutralised(self):
        self.assertEqual("'=1+1", scanner.safe_csv_cell('=1+1'))
        self.assertEqual("'  @formula", scanner.safe_csv_cell('  @formula'))
        self.assertEqual('ordinary text', scanner.safe_csv_cell('ordinary text'))

    def test_brief_command_preserves_failed_lane_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / 'run.json'
            out = Path(tmp) / 'brief.md'
            self.run['coverage'][0]['Status'] = 'Failed'
            self.run['coverage'][0]['Gaps / access failures'] = 'Search unavailable'
            run_path.write_text(json.dumps(self.run), encoding='utf-8')
            self.assertEqual(0, scanner.main(['brief', str(run_path), '--out', str(out)]))
            self.assertIn('Status: Failed', out.read_text(encoding='utf-8'))
            self.assertEqual(1, scanner.main(['brief', str(run_path), '--out', str(out)]))

    def test_csv_headers_are_unique_and_preserve_field_counts(self):
        self.assertEqual(38, len(scanner.REGISTERS['signals']))
        self.assertEqual(26, len(scanner.REGISTERS['products']))
        for headers in scanner.REGISTERS.values():
            self.assertEqual(len(headers), len(set(headers)))

    def test_export_refuses_to_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner.write_registers(self.run, tmp)
            with self.assertRaises(FileExistsError):
                scanner.write_registers(self.run, tmp)


if __name__ == '__main__':
    unittest.main()
