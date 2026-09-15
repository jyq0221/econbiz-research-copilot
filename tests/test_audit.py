import hashlib
import tempfile
import unittest
from pathlib import Path

from econbiz.audit import audit_csv


class AuditTests(unittest.TestCase):
    def audit(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'panel.csv'
            p.write_text(text, encoding='utf-8')
            before = p.read_bytes()
            report = audit_csv(p, 'firm', 'year', ['x'])
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(report['input_sha256'], hashlib.sha256(before).hexdigest())
            return report

    def test_inventory_preserves_missing_states(self):
        r = self.audit('firm,year,x\na,2023,0\na,2024,\nb,2023,未披露\nb,2024,不适用\nc,2024,匹配失败\n')
        self.assertEqual(r['rows'], 5)
        self.assertEqual(r['entities'], 3)
        self.assertEqual(r['missing']['x'], {'': 1, '未披露': 1, '不适用': 1, '匹配失败': 1})
        self.assertEqual(r['numeric']['x']['count'], 1)
        self.assertEqual(r['numeric']['x']['min'], 0)
        self.assertEqual(r['check_status'], 'passed')

    def test_duplicate_keys_are_errors_with_source_lines(self):
        r = self.audit('firm,year,x\na,2023,1\na,2023,2\n')
        issue = next(i for i in r['issues'] if i['code'] == 'duplicate_key')
        self.assertEqual(issue['lines'], [2, 3])
        self.assertEqual(r['check_status'], 'failed')

    def test_blank_keys_and_nonfinite_values_block(self):
        r = self.audit('firm,year,x\n,2023,NaN\na,,inf\n')
        self.assertTrue({'missing_key', 'nonfinite_numeric'} <= {i['code'] for i in r['issues']})
        self.assertEqual(r['check_status'], 'failed')

    def test_missing_column_and_malformed_rows(self):
        self.assertEqual(self.audit('firm,year\na,2023\n')['check_status'], 'failed')
        r = self.audit('firm,year,x\na,2023,1,extra\n')
        self.assertIn('row_width', [i['code'] for i in r['issues']])

    def test_unknown_text_not_silently_converted(self):
        r = self.audit('firm,year,x\na,2023,不知道\n')
        self.assertIn('invalid_numeric', [i['code'] for i in r['issues']])

    def test_empty_and_duplicate_headers_fail(self):
        self.assertEqual(self.audit('')['check_status'], 'failed')
        self.assertEqual(self.audit('firm,year,x,x\na,2023,1,2\n')['check_status'], 'failed')

    def test_parse_error_retains_input_evidence(self):
        r = self.audit('firm,year,x\na,2023,"unfinished\n')
        self.assertEqual(r['check_status'], 'failed')
        self.assertIn('csv_parse_error', [i['code'] for i in r['issues']])

    def test_duplicate_locations_use_physical_lines(self):
        r = self.audit('firm,year,x,note\na,2023,1,"two\nlines"\na,2023,2,single\n')
        issue = next(i for i in r['issues'] if i['code'] == 'duplicate_key')
        self.assertEqual(issue['lines'], [2, 4])
