import json
import tempfile
import unittest
from pathlib import Path

from econbiz.state import Project, WorkflowError


class StateTests(unittest.TestCase):
    def setUp(self):
        self.p = Project.create('demo', '合成面板')
        self.p.add('data', 'inventory', {'columns': ['x']})

    def valid_data(self):
        self.p.mark('data', 'completed', 'passed', '输入检查通过')

    def test_unchecked_artifact_cannot_be_consumed(self):
        with self.assertRaises(WorkflowError):
            self.p.require_usable('data')

    def test_recursive_invalidation_keeps_history(self):
        self.valid_data()
        self.p.add('result', 'result', {'coefficient': 1}, ['data'])
        self.p.mark('result', 'completed', 'passed', '数值核对')
        self.p.add('text', 'interpretation', {'text': '旧解释'}, ['result'])
        self.p.mark('text', 'completed', 'passed', '字段对照')
        self.p.revise('data', {'columns': ['new_x']}, '修改变量口径')
        self.assertEqual(self.p.artifact('text')['execution_status'], 'stale')
        self.assertEqual(self.p.snapshot()['history']['data'][0]['content']['columns'], ['x'])
        with self.assertRaises(WorkflowError):
            self.p.require_usable('result')
        with self.assertRaises(WorkflowError):
            self.p.mark('text', 'completed', 'passed', '不能直接恢复')

    def test_failed_upstream_blocks_descendants(self):
        self.valid_data()
        self.p.add('result', 'result', {}, ['data'])
        self.p.mark('result', 'completed', 'passed', 'checked')
        self.p.mark('data', 'completed', 'failed', '复查失败')
        with self.assertRaises(WorkflowError):
            self.p.require_usable('result')

    def test_no_silent_overwrite_or_missing_dependencies(self):
        with self.assertRaises(WorkflowError):
            self.p.add('data', 'inventory', {})
        with self.assertRaises(WorkflowError):
            self.p.add('x', 'result', {}, ['unknown'])

    def test_snapshot_does_not_mutate_state(self):
        self.p.artifact('data')['content']['columns'].append('fake')
        self.assertEqual(self.p.artifact('data')['content']['columns'], ['x'])

    def test_nonfinite_content_rejected(self):
        with self.assertRaises(WorkflowError):
            self.p.add('bad', 'result', {'b': float('nan')})
        self.assertNotIn('bad', self.p.snapshot()['artifacts'])

    def test_invalid_status_rejected(self):
        with self.assertRaises(WorkflowError):
            self.p.mark('data', 'success-ish', 'passed', 'bad status')

    def test_changed_source_cannot_reuse_inventory(self):
        from econbiz.audit import audit_csv
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'input.csv'
            path.write_text('firm,year,x\na,2023,1\n')
            self.p.add('source', 'inventory', audit_csv(path, 'firm', 'year', ['x']))
            self.p.mark('source', 'completed', 'passed', '检查通过')
            path.write_text('firm,year,x\na,2023,2\n')
            with self.assertRaises(WorkflowError):
                self.p.require_usable('source')

    def test_resume_marks_interrupted_work_failed(self):
        self.p.mark('data', 'running', 'pending', '开始盘点')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'research_state.json'
            self.p.save(path)
            loaded = Project.load(path)
            self.assertEqual(loaded.artifact('data')['execution_status'], 'failed')
            self.assertEqual(loaded.snapshot()['events'][-1]['action'], 'interrupted')

    def test_roundtrip_and_corrupt_state(self):
        self.valid_data()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'research_state.json'
            self.p.save(path)
            self.assertEqual(Project.load(path).snapshot(), self.p.snapshot())
            state = json.loads(path.read_text())
            state['artifacts']['data']['check_status'] = 'made_up'
            path.write_text(json.dumps(state))
            with self.assertRaises(WorkflowError):
                Project.load(path)

    def test_incomplete_historical_record_rejected(self):
        self.p.revise('data', {'columns': ['x', 'y']}, '更新盘点')
        state = self.p.snapshot()
        state['history']['data'] = [{'version': 1}]
        with self.assertRaises(WorkflowError):
            Project(state)

    def test_stale_state_cannot_be_reset_without_revision(self):
        self.valid_data()
        self.p.add('result', 'result', {}, ['data'])
        self.p.mark('result', 'completed', 'passed', 'checked')
        self.p.mark('data', 'completed', 'failed', '复查失败')
        self.p.mark('data', 'completed', 'passed', '恢复')
        with self.assertRaises(WorkflowError):
            self.p.mark('result', 'pending', 'pending', '试图清除过期标记')
