import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from test_execution import HAS_ANALYSIS, study
from econbiz.state import WorkflowError

@unittest.skipUnless(HAS_ANALYSIS, 'analysis extra not installed')
class ComparisonInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.w = study(Path(self.temp.name))
        from econbiz.execution import execute_analysis
        self.run = execute_analysis(self.w, 'r1', 'p1')

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.comparison_input'))
        from econbiz.comparison_input import load_checked_model
        return load_checked_model

    def test_actual_sample_and_parameters(self):
        model = self.api()(self.w, 'r1')
        self.assertEqual(model['sample_keys'], self.run['content']['sample']['sample_keys'])
        self.assertEqual(model['parameters'], self.run['content']['result']['parameters'])
        self.assertEqual(model['run'], {'id': 'r1', 'version': self.run['version']})
        self.assertEqual(model['sample_keys'][0][0], '000001')

    def test_changed_content_is_rejected(self):
        api = self.api()
        self.w.project._state['artifacts']['r1']['content']['result']['parameters'][0]['coefficient'] += 1
        with self.assertRaises(WorkflowError): api(self.w, 'r1')

    def test_changed_bytes_and_failed_state_rejected(self):
        api = self.api()
        path = self.w.root / self.run['content']['package'] / 'outputs/result.json'
        path.write_text('{}')
        with self.assertRaises(WorkflowError): api(self.w, 'r1')

    def test_nonresult_and_negative_check_rejected(self):
        api = self.api()
        with self.assertRaises(WorkflowError): api(self.w, 'inventory')
        self.w.project.mark('r1', 'completed', 'failed', 'test')
        with self.assertRaises(WorkflowError): api(self.w, 'r1')
