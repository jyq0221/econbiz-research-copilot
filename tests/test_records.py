import tempfile
import unittest
from pathlib import Path

from econbiz.records import validate_record
from econbiz.state import WorkflowError, now
from econbiz.workspace import Workspace


def context(question='想研究数字化'):
    return dict(question=question, known=[], unknown=['指标口径'], constraints=[], next_step='阅读说明')


def concept():
    return dict(question='数字化与风险', goal='association', rationale='讨论可能联系',
                data_gaps=['年度数据'], next_step='获取说明')


def session():
    return dict(summary='核实字段', facts=[dict(id='fact-1', claim='利润率不是波动',
                source_kind='user_quote', locator='local:session-1', excerpt='这列是年度利润率',
                evidence_status='reported')], decisions=[], outputs=[], open_questions=['窗口长度'],
                next_step='核实年份', authorization='仅讨论测量，未批准分析')


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace.create(Path(self.tmp.name) / 'study', 'study', '合成方向')

    def test_context_and_concept_without_data(self):
        for key, kind, content in [('context', 'research_context', context()), ('concept', 'concept_plan', concept())]:
            saved = self.ws.save_record(key, kind, content, reason='研究准备')
            self.assertEqual(saved['execution_status'], 'completed')
            self.assertEqual(len(saved['files']), 2)
            for ref in saved['files']:
                self.assertTrue((self.ws.root / ref['path']).exists())
        with self.assertRaises(WorkflowError):
            self.ws.project.approve('concept', '用户', '讨论', 'note')
        bad = concept()
        bad['inventory_id'] = 'invented'
        with self.assertRaises(WorkflowError):
            self.ws.save_record('bad', 'concept_plan', bad, reason='不能假造数据')

    def test_literature_requires_source_and_honest_read_scope(self):
        paper = Path(self.tmp.name) / 'abstract.txt'
        paper.write_text('合成摘要：本研究观察样本关联。', encoding='utf-8')
        self.ws.import_file('paper', paper, role='literature_source', reason='提供摘要')
        evidence = dict(source_id='paper', read_scope='abstract', locator='摘要第一段',
                        claim='作者报告样本关联', support='本研究观察样本关联', limits='仅阅读摘要')
        saved = self.ws.save_record('evidence', 'literature_evidence', evidence, reason='阅读摘要')
        self.assertEqual(saved['dependencies'], {'paper': 1})
        for change in ({'source_id': 'missing'}, {'read_scope': 'metadata'}, {'locator': ''}):
            with self.assertRaises(WorkflowError):
                self.ws.save_record('bad', 'literature_evidence', dict(evidence, **change), reason='校验')
        self.ws.save_record('concept', 'concept_plan', concept(), dependencies=['evidence'], reason='依据文献')
        evidence['claim'] = '修正：仅报告特定样本关联'
        self.ws.save_record('evidence', 'literature_evidence', evidence, reason='更正')
        self.assertEqual(self.ws.project.artifact('concept')['check_status'], 'stale')
        self.assertEqual(self.ws.project.version('evidence', 1)['content']['claim'], '作者报告样本关联')

    def test_session_provenance_and_corrections(self):
        first = self.ws.save_record('session-1', 'session_note', session(), reason='保存可见讨论')
        changed = session()
        changed['facts'][0]['claim'] = '该列是合并利润率'
        self.ws.save_record('session-1', 'session_note', changed, reason='用户更正')
        self.assertEqual(first['version'], 1)
        self.assertEqual(Workspace.open(self.ws.root).project.artifact('session-1')['content'], changed)
        for change in ({'facts': [{'claim': '没有来源'}]}, {'platform_thread_id': 'invented'}):
            with self.assertRaises(WorkflowError):
                self.ws.save_record('bad', 'session_note', dict(session(), **change), reason='校验')

    def test_decision_saves_quote_without_approving_and_binds_version(self):
        from test_plans import candidate
        from econbiz.plans import register_plan
        self.ws.project.add('inventory', 'inventory', {'columns': ['firm', 'year', 'x', 'y']})
        self.ws.project.mark('inventory', 'completed', 'passed', '合成字段')
        register_plan(self.ws.project, 'plan', candidate(), 'inventory')
        decision = dict(plan_id='plan', plan_version=1, quote='按这份方案做', scope='当前方案', recorded_at=now())
        self.ws.save_record('decision', 'user_decision', decision, reason='可见摘录')
        self.assertEqual(self.ws.project.snapshot()['decisions'], [])
        for version in (0, 2, True):
            with self.assertRaises(WorkflowError):
                self.ws.save_record('bad', 'user_decision', dict(decision, plan_version=version), reason='校验')

    def test_tasks_require_actual_outputs_and_reject_unknown_records(self):
        task = dict(title='查资料', task_status='completed', input_versions={}, outputs=[], next_step='写草案', blocked_reason='')
        with self.assertRaises(WorkflowError):
            self.ws.save_record('task', 'research_task', task, reason='不能虚报完成')
        self.ws.save_record('context', 'research_context', context(), reason='已整理')
        task['outputs'] = [{'artifact_id': 'context', 'version': 1}]
        saved = self.ws.save_record('task', 'research_task', task, reason='输出可读')
        self.assertEqual(saved['content']['task_status'], 'completed')
        with self.assertRaises(WorkflowError):
            self.ws.save_record('bad', 'research_task', dict(task, task_status='waiting'), reason='缺等待理由')
        with self.assertRaises(WorkflowError):
            validate_record('made_up', {}, self.ws.project)
