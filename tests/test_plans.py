import unittest

from econbiz.plans import register_plan, require_approved_plan
from econbiz.state import Project, WorkflowError


def candidate():
    return {
        'question': '合成指标 x 与 y 的条件关联', 'goal': 'association',
        'judgment': '非定向探索', 'competing_explanations': '遗漏混杂',
        'mapping': {'x': {'field': 'x', 'definition': '原值', 'unit': '指数',
                          'time': '会计年度', 'source': '合成数据', 'version': '1'},
                    'y': {'field': 'y', 'definition': '原值', 'unit': '比例',
                          'time': '会计年度', 'source': '合成数据', 'version': '1'}},
        'sample': '全部有效企业年度', 'comparison': '企业内跨期差异',
        'missing_rule': '逐项报告后完整案例分析，不填零',
        'model': 'linear_fe', 'controls': [], 'fixed_effects': ['firm', 'year'],
        'standard_errors': {'method': 'cluster', 'field': 'firm', 'rationale': '同企业误差相关'},
        'conditions': 'X 在吸收固定效应后仍有变化，待估计阶段检查',
        'feasibility': '待模型诊断', 'data_gaps': [], 'priority_reason': '用于验证基础流程',
        'boundary': '仅条件关联', 'relation': '主要方案', 'purpose': 'planned',
    }


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.p = Project.create('demo', '测试')
        self.p.add('data', 'inventory', {'columns': ['firm', 'year', 'x', 'y']})
        self.p.mark('data', 'completed', 'passed', 'checked')

    def test_approval_gate_and_version_binding(self):
        register_plan(self.p, 'p1', candidate(), 'data')
        with self.assertRaises(WorkflowError):
            require_approved_plan(self.p, 'p1')
        self.p.approve('p1', '研究者', '核对概念与样本规则', 'decisions/001.md')
        self.assertEqual(require_approved_plan(self.p, 'p1')['version'], 1)
        changed = candidate()
        changed['sample'] = '只保留2024年'
        self.p.revise('p1', changed, '改变样本')
        with self.assertRaises(WorkflowError):
            require_approved_plan(self.p, 'p1')
        self.assertEqual(len(self.p.snapshot()['decisions']), 1)

    def test_nonexistent_fields_rejected(self):
        for change in ('mapping', 'controls', 'fixed_effects', 'standard_errors'):
            c = candidate()
            if change == 'mapping': c['mapping']['x']['field'] = 'invented'
            elif change == 'standard_errors': c[change]['field'] = 'invented'
            else: c[change] = ['invented']
            with self.assertRaises(WorkflowError):
                register_plan(self.p, change, c, 'data')

    def test_unsupported_design_preserved_but_blocked(self):
        c = candidate()
        c.update(goal='causal', model='did')
        register_plan(self.p, 'p1', c, 'data')
        self.assertEqual(self.p.artifact('p1')['content']['goal'], 'causal')
        with self.assertRaises(WorkflowError):
            self.p.approve('p1', '研究者', '想继续', 'decision.md')

    def test_incomplete_plan_rejected(self):
        c = candidate()
        del c['missing_rule']
        with self.assertRaises(WorkflowError):
            register_plan(self.p, 'p1', c, 'data')

    def test_stale_inventory_invalidates_approval(self):
        register_plan(self.p, 'p1', candidate(), 'data')
        self.p.approve('p1', '研究者', '已核对', 'decision.md')
        self.p.revise('data', {'columns': ['firm', 'year', 'x', 'y']}, '输入数据更新')
        with self.assertRaises(WorkflowError):
            require_approved_plan(self.p, 'p1')

    def test_approval_requires_actor_reason_evidence(self):
        register_plan(self.p, 'p1', candidate(), 'data')
        with self.assertRaises(WorkflowError):
            self.p.approve('p1', '', '', '')

    def test_unknown_inference_option_cannot_be_approved(self):
        c = candidate()
        c['standard_errors']['method'] = 'magic'
        register_plan(self.p, 'p1', c, 'data')
        with self.assertRaises(WorkflowError):
            self.p.approve('p1', '研究者', '检查选项', 'decision.md')

    def test_fe_model_requires_fixed_effects(self):
        c = candidate()
        c['fixed_effects'] = []
        register_plan(self.p, 'p1', c, 'data')
        with self.assertRaises(WorkflowError):
            self.p.approve('p1', '研究者', '检查选项', 'decision.md')
