import unittest

from econbiz.plans import register_plan, revise_plan
from econbiz.research_history import has_prior_results
from econbiz.state import Project, WorkflowError
from test_plans import candidate


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.p = Project.create('study', '测试')
        self.p.add('data', 'inventory', {'columns': ['firm', 'year', 'x', 'y']})
        self.p.mark('data', 'completed', 'passed', 'checked')

    def result(self):
        self.p.add('result', 'result', {'coefficient': 0.0}, ['data'])
        self.p.mark('result', 'completed', 'passed', '合成结果')

    def test_all_plan_entries_require_exploration_after_results(self):
        register_plan(self.p, 'before', candidate(), 'data')
        self.result()
        before = self.p.snapshot()
        changed = dict(candidate(), question='新的研究问题')
        actions = [lambda: register_plan(self.p, 'after', candidate(), 'data'),
                   lambda: revise_plan(self.p, 'before', changed, '结果后修改', 'data'),
                   lambda: self.p.revise('before', changed, '通用入口'),
                   lambda: self.p.add('direct', 'plan', candidate(), ['data'])]
        for action in actions:
            with self.assertRaises(WorkflowError):
                action()
            self.assertEqual(self.p.snapshot(), before)
        changed['exploration_reason'] = '看到结果后核实替代测量'
        saved = revise_plan(self.p, 'before', changed, '说明原因', 'data')
        self.assertEqual(saved['content']['purpose'], 'exploratory')
        self.p.revise('result', {'error': '重跑失败'}, '保留历史')
        self.assertTrue(has_prior_results(self.p))

    def test_later_approval_does_not_reclassify_unchanged_plan(self):
        register_plan(self.p, 'before', candidate(), 'data')
        self.result()
        self.p.approve('before', '用户', '确认原方案', 'quote.md')
        self.assertEqual(self.p.artifact('before')['content']['purpose'], 'planned')

    def test_evidence_context_dependencies_and_failed_revisions(self):
        for key, kind in [('evidence', 'literature_evidence'), ('context', 'session_note')]:
            self.p.add(key, kind, {})
            self.p.mark(key, 'completed', 'passed', '结构记录')
        register_plan(self.p, 'plan', candidate(), 'data', evidence_ids=['evidence'], context_ids=['context'])
        self.assertEqual(self.p.artifact('plan')['dependencies'], {'data': 1, 'evidence': 1, 'context': 1})
        self.p.revise('evidence', {}, '文献更正')
        self.assertEqual(self.p.artifact('plan')['execution_status'], 'stale')
        self.p.mark('evidence', 'completed', 'passed', '更正已保存')
        revise_plan(self.p, 'plan', candidate(), '重选依据', 'data', context_ids=['context'])
        self.assertNotIn('evidence', self.p.artifact('plan')['dependencies'])
        before = self.p.snapshot()
        with self.assertRaises(WorkflowError):
            revise_plan(self.p, 'plan', candidate(), '错误依据', 'data', evidence_ids=['context'])
        self.assertEqual(self.p.snapshot(), before)

    def test_direct_revision_cannot_drop_inventory_or_use_unknown_fields(self):
        register_plan(self.p, 'plan', candidate(), 'data')
        before = self.p.snapshot()
        bad = candidate()
        bad['mapping']['x']['field'] = 'invented'
        for content, deps in [(bad, ['data']), (candidate(), [])]:
            with self.assertRaises(WorkflowError):
                self.p.revise('plan', content, '必须验证', dependencies=deps)
            self.assertEqual(self.p.snapshot(), before)
