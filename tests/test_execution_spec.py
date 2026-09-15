import copy
import unittest

from econbiz.state import WorkflowError
from test_plans import candidate


def executable_plan():
    plan = candidate()
    plan['execution'] = dict(sample_filters=[], missing='complete_case',
                             singleton='keep', confidence=0.95)
    return plan


INVENTORY = {'columns': ['firm', 'year', 'x', 'y', 'c'],
             'key': {'entity': 'firm', 'time': 'year'}}
RAW = b'firm,year,x,y,c\n001,2020,1,2,9\n001,2021,2,4,NA\n002,2020,3,,1\n002,2021,4,8,5\n'


class ExecutionSpecTests(unittest.TestCase):
    def api(self):
        import econbiz
        self.assertIsNotNone(__import__('importlib').util.find_spec('econbiz.execution_spec'),
                             'execution_spec must exist')
        from econbiz.execution_spec import compile_spec, prepare_sample
        return compile_spec, prepare_sample

    def test_filters_complete_cases_and_control_loss_are_counted(self):
        compile_spec, prepare_sample = self.api()
        plan = executable_plan()
        plan['controls'] = ['c']
        spec = compile_spec(plan, INVENTORY)
        rows, audit = prepare_sample(RAW, spec)
        self.assertEqual([r['firm'] for r in rows], ['001', '002'])
        self.assertEqual(audit['input_rows'], 4)
        self.assertEqual(audit['final_rows'], 2)
        self.assertEqual(audit['missing_by_field']['c'], {'NA': 1})
        self.assertEqual(audit['baseline_complete_rows'], 3)
        self.assertEqual(audit['control_additional_loss'], 1)
        self.assertEqual(sum(s['dropped'] for s in audit['steps']), 2)
        plan['execution']['sample_filters'] = [{'field': 'year', 'op': 'ge', 'value': 2021}]
        rows, audit = prepare_sample(RAW, compile_spec(plan, INVENTORY))
        self.assertEqual(len(rows), 1)
        self.assertEqual(audit['steps'][0]['remaining'], 2)

    def test_no_invented_or_unknown_execution_rules(self):
        compile_spec, _ = self.api()
        mutations = [lambda p: p.pop('execution'),
                     lambda p: p['execution'].update(missing='fill_zero'),
                     lambda p: p['execution'].update(winsor=0.01),
                     lambda p: p.update(controls=['x']),
                     lambda p: p.update(fixed_effects=['c']),
                     lambda p: p['execution'].update(sample_filters=[{'field': 'z', 'op': 'eq', 'value': '1'}]),
                     lambda p: p['execution'].update(sample_filters=[{'field': 'year', 'op': 'python', 'value': '1'}])]
        for mutate in mutations:
            p = executable_plan()
            mutate(p)
            with self.subTest(p=p), self.assertRaises(WorkflowError):
                compile_spec(p, INVENTORY)

    def test_bad_numbers_keys_and_duplicates_never_silently_drop(self):
        compile_spec, prepare_sample = self.api()
        spec = compile_spec(executable_plan(), INVENTORY)
        for raw in [RAW.replace(b',4,8,', b',inf,8,'), RAW.replace(b',4,8,', b',oops,8,'),
                    RAW + b'001,2020,1,2,9\n', RAW.replace(b'2020', b'2020.5'),
                    RAW.replace(b'001,2020', b',2020')]:
            with self.subTest(raw=raw), self.assertRaises(WorkflowError):
                prepare_sample(raw, spec)

    def test_filters_do_not_evaluate_expressions_or_coerce_codes(self):
        compile_spec, prepare_sample = self.api()
        p = executable_plan()
        p['execution']['sample_filters'] = [{'field': 'firm', 'op': 'in', 'value': ['001']}]
        rows, audit = prepare_sample(RAW, compile_spec(p, INVENTORY))
        self.assertEqual(len(rows), 2)
        self.assertEqual(audit['sample_keys'], [['001', '2020'], ['001', '2021']])

    def test_description_uses_mapped_fields(self):
        compile_spec, prepare_sample = self.api()
        p = executable_plan()
        p.update(goal='description', model='descriptive', controls=[], fixed_effects=[])
        spec = compile_spec(p, INVENTORY)
        self.assertEqual(spec['estimation']['x'], ['x', 'y'])
        self.assertIsNone(spec['estimation']['y'])
        self.assertEqual(len(prepare_sample(RAW, spec)[0]), 3)
