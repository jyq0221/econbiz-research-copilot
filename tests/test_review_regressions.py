import tempfile
import unittest
from pathlib import Path

from econbiz.checkpoints import restore_record
from econbiz.plans import register_plan
from econbiz.state import WorkflowError, now
from econbiz.workspace import Workspace
from test_plans import candidate
from test_records import context, session


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace.create(Path(self.tmp.name) / 'study', 'study', '合成测试')

    def test_view_symlink_never_overwrites_original_material(self):
        source = Path(self.tmp.name) / 'input.csv'
        source.write_bytes(b'firm,year,x\na,2024,1\n')
        saved = self.ws.import_file('source', source, role='raw_data', reason='首批')
        material = self.ws.root / saved['files'][0]['path']
        before = material.read_bytes()
        view = self.ws.root / '研究进展.md'
        view.unlink()
        view.symlink_to(material)
        receipt = self.ws.save()
        self.assertEqual(material.read_bytes(), before)
        self.assertTrue(receipt['state_saved'])
        self.assertFalse(receipt['view_saved'])

    def test_state_symlink_never_overwrites_another_file(self):
        material = self.ws.root / 'data' / 'original.txt'
        material.write_bytes(b'original')
        state = self.ws.root / 'research_state.json'
        state.unlink()
        state.symlink_to(material)
        with self.assertRaises(WorkflowError):
            self.ws.save()
        self.assertEqual(material.read_bytes(), b'original')

    def test_old_decision_quote_cannot_approve_new_plan_version(self):
        p = self.ws.project
        p.add('data', 'inventory', {'columns': ['firm', 'year', 'x', 'y']})
        p.mark('data', 'completed', 'passed', '合成')
        register_plan(p, 'plan', candidate(), 'data')
        decision = self.ws.save_record('decision', 'user_decision', dict(plan_id='plan', plan_version=1,
                  quote='【测试】按此方案', scope='plan v1', recorded_at=now()), reason='合成授权')
        evidence = decision['files'][0]['path']
        p = self.ws.project
        p.revise('plan', dict(candidate(), question='另一问题'), '新版本')
        with self.assertRaises(WorkflowError):
            p.approve('plan', '用户', '不能复用旧摘录', evidence)
        with self.assertRaises(WorkflowError):
            p.approve('plan', '用户', '路径别名也不能复用', evidence.replace('/v0001/', '/v0001/../v0001/'))
        self.assertEqual(p.snapshot()['decisions'], [])

    def test_overlapping_layout_is_rejected(self):
        layout = self.ws.project.artifact('workspace-layout')['content']
        layout['research_history'] = 'data/raw/source/v0001'
        self.ws.project.revise('workspace-layout', layout, '错误映射')
        with self.assertRaises(WorkflowError):
            Workspace(self.ws.root, self.ws.project)

    def test_changed_task_output_blocks_all_consumers(self):
        self.ws.save_record('output', 'research_context', context(), reason='输出')
        task = dict(title='整理', task_status='completed', input_versions={},
                    outputs=[{'artifact_id': 'output', 'version': 1}], next_step='继续', blocked_reason='')
        self.ws.save_record('task', 'research_task', task, reason='完成')
        self.ws.save_record('output', 'research_context', context('更正后'), reason='更正')
        with self.assertRaises(WorkflowError):
            self.ws.project.require_usable('task')

    def test_restored_result_requires_fresh_numerical_check(self):
        p = self.ws.project
        p.add('result', 'result', {'coefficient': 0.0})
        p.mark('result', 'completed', 'passed', '合成旧记录')
        p.revise('result', {'error': 'failed'}, '新版失败')
        p.mark('result', 'failed', 'failed', '运行错误')
        restored = restore_record(self.ws, 'result', 1, '读取历史')
        self.assertNotEqual(restored['check_status'], 'passed')
        with self.assertRaises(WorkflowError):
            self.ws.project.require_usable('result')

    def test_session_cannot_present_old_output_as_current(self):
        self.ws.save_record('output', 'research_context', context(), reason='输出')
        note = session()
        note['outputs'] = [{'artifact_id': 'output', 'version': 1}]
        self.ws.save_record('session', 'session_note', note, reason='摘要')
        self.ws.save_record('output', 'research_context', context('新问题'), reason='更正')
        with self.assertRaises(WorkflowError):
            self.ws.project.require_usable('session')

    def test_external_result_exposure_also_marks_later_plans_exploratory(self):
        from econbiz.research_history import has_prior_results
        table = Path(self.tmp.name) / 'regression.txt'
        table.write_text('合成外部表：coef=0.2；未复现', encoding='utf-8')
        self.ws.import_file('external', table, role='external_result', reason='用户给出的结果')
        self.assertTrue(has_prior_results(self.ws.project))
