import importlib.util
import tempfile
import unittest
from pathlib import Path

from econbiz.state import WorkflowError
from econbiz.workspace import Workspace


class AnalysisInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.w = Workspace.create(self.root / 'study', 'study', '合成输入测试')

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.analysis_input'), 'input adapter missing')
        from econbiz.analysis_input import import_table
        return import_table

    def test_csv_preserves_bytes_and_can_be_audited(self):
        import_table = self.api()
        path = self.root / 'source.csv'
        raw = 'firm,year,x\n000001,2024,未披露\n'.encode()
        path.write_bytes(raw)
        self.w.import_file('raw', path, role='raw_data', reason='合成数据')
        converted = import_table(self.w, 'table', 'raw')
        self.assertEqual(converted['kind'], 'source')
        self.assertEqual(len(converted['files']), 1)
        self.assertEqual((self.w.root / converted['files'][0]['path']).read_bytes(), raw)
        inv = self.w.audit('inventory', 'table', entity='firm', time='year', numeric=['x'])
        self.assertEqual(inv['check_status'], 'passed')
        self.assertEqual(path.read_bytes(), raw)

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'), 'analysis extra not installed')
    def test_xlsx_sheet_text_codes_metadata_and_formula_rejection(self):
        import_table = self.api()
        import openpyxl
        path = self.root / 'source.xlsx'
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = '数据'
        sheet.append(['firm', 'year', 'x'])
        sheet.append(['000001', 2024, 'NA'])
        book.save(path)
        self.w.import_file('raw', path, role='raw_data', reason='合成表格')
        with self.assertRaises(WorkflowError):
            import_table(self.w, 'missing-sheet', 'raw')
        result = import_table(self.w, 'table', 'raw', sheet='数据')
        raw = (self.w.root / result['files'][0]['path']).read_text()
        self.assertIn('000001,2024,NA', raw)
        self.assertEqual(result['content']['conversion']['sheet'], '数据')
        sheet['C2'] = '=1+1'
        book.save(path)
        self.w.import_file('formula', path, role='raw_data', reason='公式测试')
        with self.assertRaisesRegex(WorkflowError, '公式'):
            import_table(self.w, 'bad', 'formula', sheet='数据')

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'), 'analysis extra not installed')
    def test_formatted_numeric_codes_are_reported_not_silently_reconstructed(self):
        import_table = self.api()
        import openpyxl
        path = self.root / 'codes.xlsx'
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(['firm', 'year'])
        sheet.append([1, 2024])
        sheet['A2'].number_format = '000000'
        book.save(path)
        self.w.import_file('raw', path, role='raw_data', reason='编码测试')
        with self.assertRaisesRegex(WorkflowError, '格式|文本'):
            import_table(self.w, 'bad', 'raw', sheet=sheet.title)
