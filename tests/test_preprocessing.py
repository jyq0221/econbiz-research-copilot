import csv
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from econbiz.state import WorkflowError


STATA_PATH = os.environ.get('ECONBIZ_TEST_STATA')
HAS_STATA = bool(STATA_PATH and Path(STATA_PATH).is_file())


def recipe(*steps):
    return {'schema_version': 1, 'keys': ['firm', 'year'], 'steps': list(steps)}


def rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode())))


class PreprocessingTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.preprocessing'), 'preprocessing module missing')
        from econbiz.preprocessing import prepare_data, merge_data
        return prepare_data, merge_data

    def native(self, raw, spec, *, succeeds=True):
        from econbiz.preprocessing_script import render_preparation_script
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'input.csv').write_bytes(raw)
            (root / 'prepare.do').write_text(render_preparation_script(spec, backend='stata'))
            subprocess.run([STATA_PATH, '-b', '-q', 'do', 'prepare.do'], cwd=root, capture_output=True, timeout=40)
            log = (root / 'prepare.log').read_text(errors='replace')
            if not succeeds:
                self.assertFalse((root / 'preparation-audit.json').exists(), log[-3000:])
                self.assertFalse((root / 'processed.csv').exists(), log[-3000:])
                return
            self.assertTrue((root / 'processed.csv').exists(), log[-4000:])
            self.assertTrue((root / 'preparation-audit.json').exists(), log[-4000:])
            return (root / 'processed.csv').read_bytes(), json.loads((root / 'preparation-audit.json').read_text())

    def test_ordered_group_winsor_retains_raw_and_current_filter_sample(self):
        prepare, _ = self.api()
        raw = b'firm,year,group,x\n001,2020,A,1\n002,2020,A,3\n003,2020,A,100\n004,2020,B,10\n005,2020,B,20\n006,2020,A,\n'
        out, audit = prepare(raw, recipe(
            dict(op='filter', source='firm', operator='ne', value='003'),
            dict(op='winsor', source='x', target='x_w', lower=.25, upper=.75, by=['group']),
            dict(op='ln', source='x_w', target='ln_x', invalid='error')))
        result = rows(out)
        self.assertEqual([r['firm'] for r in result], ['001', '002', '004', '005', '006'])
        self.assertEqual([r['x'] for r in result], ['1', '3', '10', '20', ''])
        self.assertEqual([r['x_w'] for r in result], ['1.5', '2.5', '12.5', '17.5', ''])
        self.assertAlmostEqual(float(result[0]['ln_x']), math.log(1.5))
        self.assertEqual(audit['n_before'], 6)
        self.assertEqual(audit['n_after'], 5)
        self.assertEqual(audit['steps'][1]['affected'], 4)
        self.assertEqual(audit['steps'][1]['groups'][0]['lower_threshold'], 1.5)
        self.assertEqual(audit['verification'], 'not_independently_verified')

    def test_explicit_transforms_and_group_standard_deviation(self):
        prepare, _ = self.api()
        raw = b'firm,year,x,d,category\n001,1,1,2,A\n002,1,3,0,B\n003,1,,4,\n'
        out, audit = prepare(raw, recipe(
            dict(op='ratio', numerator='x', denominator='d', target='r', zero='missing'),
            dict(op='interaction', sources=['x', 'd'], target='xd'),
            dict(op='indicator', source='category', target='is_a', value='A', missing='missing'),
            dict(op='center', source='x', target='xc', by=[]),
            dict(op='standardize', source='x', target='xz', by=[], ddof=1, zero='error'),
            dict(op='log1p', source='x', target='lx', invalid='missing')))
        result = rows(out)
        self.assertEqual([r['r'] for r in result], ['0.5', '', ''])
        self.assertEqual([r['xd'] for r in result], ['2', '0', ''])
        self.assertEqual([r['is_a'] for r in result], ['1', '0', ''])
        self.assertEqual([r['xc'] for r in result], ['-1', '1', ''])
        self.assertAlmostEqual(float(result[0]['xz']), -1 / math.sqrt(2))
        self.assertAlmostEqual(audit['steps'][4]['groups'][0]['sd'], math.sqrt(2))

    def test_panel_lag_and_difference_use_exact_time_gaps_and_keep_order(self):
        prepare, _ = self.api()
        raw = b'firm,year,x\n001,2023,8\n001,2020,1\n002,2021,50\n001,2021,3\n002,2020,20\n'
        out, audit = prepare(raw, recipe(
            dict(op='lag', source='x', target='lag_x', entity=['firm'], time='year', interval=1),
            dict(op='difference', source='x', target='dx', entity=['firm'], time='year', interval=1)))
        result = rows(out)
        self.assertEqual([r['lag_x'] for r in result], ['', '', '20', '1', ''])
        self.assertEqual([r['dx'] for r in result], ['', '', '30', '2', ''])
        self.assertEqual(audit['steps'][0]['unmatched_periods'], 3)

    def test_domain_missing_and_malformed_numbers_are_distinct(self):
        prepare, _ = self.api()
        rule = dict(op='ln', source='x', target='lx', invalid='missing')
        out, audit = prepare(b'firm,year,x\n001,1,-1\n002,1,\n', recipe(rule))
        self.assertEqual([r['lx'] for r in rows(out)], ['', ''])
        self.assertEqual(audit['steps'][0]['invalid_to_missing'], 1)
        for value in ['NA', 'unreported', 'NaN', 'inf', '1e309', ' ']:
            with self.subTest(value=value), self.assertRaises(WorkflowError):
                prepare(f'firm,year,x\n001,1,{value}\n'.encode(), recipe(rule))
        with self.assertRaises(WorkflowError):
            prepare(b'firm,year,x\n001,1,0\n', recipe(dict(rule, invalid='error')))

    def test_recipe_rejects_typos_overwrites_and_ambiguous_keys(self):
        prepare, _ = self.api()
        raw = b'firm,year,x\n001,1,1\n'
        bad = [dict(op='ln', source='x', target='x', invalid='error'),
               dict(op='ln', source='x', target='y', invlaid='error'),
               dict(op='winsor', source='x', target='y', lower=.9, upper=.1, by=[]),
               dict(op='standardize', source='x', target='y', by=[], ddof=True, zero='missing'),
               dict(op='lag', source='x', target='y', entity=['firm'], time='year', interval=.5)]
        for step in bad:
            with self.subTest(step=step), self.assertRaises(WorkflowError):
                prepare(raw, recipe(step))
        for raw in [b'firm,year,x\n001,1,1\n001,1,2\n', b'firm,year,x\n,1,1\n']:
            with self.assertRaises(WorkflowError):
                prepare(raw, recipe())
        with self.assertRaises(WorkflowError):
            prepare(b'firm,year,x\n001,1.5,1\n', recipe(dict(op='lag', source='x', target='y', entity=['firm'], time='year', interval=1)))

    def test_validation_reports_wrong_types_and_numeric_overflow_as_workflow_errors(self):
        prepare, _ = self.api()
        base = dict(op='ln', source='x', target='lx', invalid='error')
        cases = [recipe(dict(base, invalid=[])), recipe(dict(op='filter', source='x', operator=[])),
                 recipe(dict(op='winsor', source='x', target='z', lower=10**500, upper=1, by=[])),
                 dict(recipe(), schema_version=True)]
        for spec in cases:
            with self.subTest(spec=spec), self.assertRaises(WorkflowError):
                prepare(b'firm,year,x\n001,1,1\n', spec)
        for text in ['1_000', '１２', '1d3']:
            with self.subTest(text=text), self.assertRaises(WorkflowError):
                prepare(f'firm,year,x\n001,1,{text}\n'.encode(), recipe(base))
        with self.assertRaises(WorkflowError):
            prepare(b'firm,year,x\n001,9007199254740993,1\n', recipe(dict(op='lag', source='x', target='y', entity=['firm'], time='year', interval=1)))
        with self.assertRaises(WorkflowError):
            prepare(b'firm,year,x,d\n001,1,1e300,1e300\n', recipe(dict(op='interaction', sources=['x', 'd'], target='y')))

    def test_all_missing_groups_and_empty_filtered_output_remain_explicit(self):
        prepare, _ = self.api()
        raw = b'firm,year,x\n001,1,\n002,1,\n'
        out, audit = prepare(raw, recipe(dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='error')))
        self.assertEqual([r['z'] for r in rows(out)], ['', ''])
        self.assertIsNone(audit['steps'][0]['groups'][0]['sd'])
        out, audit = prepare(raw, recipe(dict(op='filter', source='firm', operator='eq', value='none'),
                                         dict(op='center', source='x', target='xc', by=[])))
        self.assertEqual(rows(out), [])
        self.assertEqual(out.decode().strip(), 'firm,year,x,xc')
        self.assertEqual(audit['n_after'], 0)

    def test_merge_cardinality_unmatched_and_column_conflicts(self):
        _, merge = self.api()
        left = b'firm,year,x\n001,1,10\n001,2,20\n002,1,30\n'
        right = b'firm,z\n001,A\n003,C\n'
        out, audit = merge(left, right, keys=['firm'], relationship='many_to_one', how='left')
        self.assertEqual([r['z'] for r in rows(out)], ['A', 'A', ''])
        self.assertEqual(audit['left_unmatched_rows'], 1)
        self.assertEqual(audit['right_unmatched_rows'], 1)
        inner, _ = merge(left, right, keys=['firm'], relationship='many_to_one', how='inner')
        self.assertEqual(len(rows(inner)), 2)
        with self.assertRaises(WorkflowError):
            merge(left, right, keys=['firm'], relationship='one_to_one', how='left')
        for invalid in [b'firm,z\n001,A\n001,B\n', b'firm,z\n,A\n', b'firm,x\n001,99\n']:
            with self.assertRaises(WorkflowError):
                merge(left, invalid, keys=['firm'], relationship='many_to_one', how='left')

    def test_python_script_executes_and_writes_audit(self):
        self.api()
        self.assertIsNotNone(importlib.util.find_spec('econbiz.preprocessing_script'))
        from econbiz.preprocessing_script import render_preparation_script
        spec = recipe(dict(op='ln', source='x', target='lx', invalid='error'))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'input.csv').write_bytes(b'firm,year,x\n001,1,1\n002,1,2\n')
            (root / 'prepare.py').write_text(render_preparation_script(spec, backend='python'))
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            result = subprocess.run([sys.executable, str(root / 'prepare.py')], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertAlmostEqual(float(rows((root / 'processed.csv').read_bytes())[1]['lx']), math.log(2))
            self.assertEqual(json.loads((root / 'preparation-audit.json').read_text())['n_after'], 2)

    def test_generator_rejects_unsafe_names_paths_and_backends(self):
        self.api()
        from econbiz.preprocessing_script import render_preparation_script
        spec = recipe(dict(op='ln', source='x', target='lx', invalid='error'))
        for backend, kwargs in [('ruby', {}), ('stata', {'input_name': '../x.csv'}),
                                ('python', {'output_name': 'input.csv'})]:
            with self.subTest(backend=backend, kwargs=kwargs), self.assertRaises(WorkflowError):
                render_preparation_script(spec, backend=backend, **kwargs)
        with self.assertRaises(WorkflowError):
            render_preparation_script(recipe(dict(op='ln', source='x;erase', target='lx', invalid='error')), backend='stata')
        with self.assertRaises(WorkflowError):
            render_preparation_script(recipe(dict(op='filter', source='x', operator='le', value=1e308)), backend='stata')
        with self.assertRaises(WorkflowError):
            render_preparation_script(recipe(dict(op='filter', source='x', operator='lt', value=9007199254740993)), backend='stata')

    def test_standard_deviation_preserves_large_and_tiny_finite_scales(self):
        prepare, _ = self.api()
        step = dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='missing')
        for raw, expected in [(b'firm,year,x\n001,1,-1e200\n002,1,-1\n003,1,1\n004,1,1e200\n', -math.sqrt(1.5)),
                              (b'firm,year,x\n001,1,1e-200\n002,1,2e-200\n', -1/math.sqrt(2))]:
            out, audit = prepare(raw, recipe(step))
            self.assertAlmostEqual(float(rows(out)[0]['z']), expected)
            self.assertGreater(audit['steps'][0]['groups'][0]['sd'], 0)

    def test_constant_group_standardization_uses_zero_policy_without_rounding_noise(self):
        prepare, _ = self.api()
        spec = recipe(dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='missing'))
        for value in ['-59.6260997496342', '5e-324']:
            raw = f'firm,year,x\n001,1,{value}\n002,1,{value}\n003,1,{value}\n'.encode()
            actual, audit = prepare(raw, spec)
            with self.subTest(value=value):
                self.assertEqual([row['z'] for row in rows(actual)], ['', '', ''])
                self.assertEqual(audit['steps'][0]['groups'][0]['sd'], 0)

    @unittest.skipUnless(HAS_STATA, 'set ECONBIZ_TEST_STATA to opt into native Stata')
    def test_native_stata_matches_hand_computable_recipe_and_preserves_csv_values(self):
        self.api()
        self.assertIsNotNone(importlib.util.find_spec('econbiz.preprocessing_script'))
        from econbiz.preprocessing_script import render_preparation_script
        spec = recipe(
            dict(op='filter', source='year', operator='ge', value=2020),
            dict(op='winsor', source='x', target='x_w', lower=.25, upper=.75, by=['group']),
            dict(op='ln', source='x_w', target='ln_x', invalid='error'),
            dict(op='log1p', source='x', target='lp_x', invalid='missing'),
            dict(op='ratio', numerator='x', denominator='d', target='ratio', zero='missing'),
            dict(op='interaction', sources=['x', 'd'], target='xd'),
            dict(op='indicator', source='group', target='is_a', value='A', missing='missing'),
            dict(op='center', source='x', target='xc', by=['group']),
            dict(op='standardize', source='x', target='xz', by=['group'], ddof=1, zero='missing'),
            dict(op='lag', source='x', target='lag_x', entity=['firm'], time='year', interval=1),
            dict(op='difference', source='x', target='dx', entity=['firm'], time='year', interval=1))
        raw = 'firm,year,group,x,d,note\r\n001,2020,A,1,2,"中文, quote ""x""\r\nnext"\r\n001,2021,A,3,0,a\r\n001,2023,A,100,1,b\r\n002,2020,B,10,5,c\r\n002,2021,B,20,2,d\r\n003,2020,A,,2," space "\r\n'.encode()
        expected, _ = self.api()[0](raw, spec)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'input.csv').write_bytes(raw)
            (root / 'prepare.do').write_text(render_preparation_script(spec, backend='stata'))
            result = subprocess.run([STATA_PATH, '-b', '-q', 'do', 'prepare.do'], cwd=root, capture_output=True, timeout=40)
            log = (root / 'prepare.log').read_text(errors='replace') if (root / 'prepare.log').exists() else str(result)
            self.assertTrue((root / 'processed.csv').exists(), log[-7000:])
            got_rows, wanted_rows = rows((root / 'processed.csv').read_bytes()), rows(expected)
            self.assertEqual(len(got_rows), len(wanted_rows))
            originals = {'firm', 'year', 'group', 'x', 'd', 'note'}
            for got, want in zip(got_rows, wanted_rows):
                self.assertEqual(set(got), set(want))
                for name, value in want.items():
                    if name in originals or value == '':
                        self.assertEqual(got[name], value, name)
                    else:
                        self.assertAlmostEqual(float(got[name]), float(value), places=11, msg=name)
            self.assertTrue((root / 'preparation-audit.json').exists(), log[-5000:])
            audit = json.loads((root / 'preparation-audit.json').read_text())
            self.assertEqual(audit['n_before'], 6)
            self.assertEqual(audit['n_after'], 6)
            self.assertEqual(audit['steps'][1]['groups'][0]['lower_threshold'], 2)
            self.assertEqual(audit['verification'], 'not_independently_verified')

    @unittest.skipUnless(HAS_STATA, 'set ECONBIZ_TEST_STATA to opt into native Stata')
    def test_native_empty_missing_domain_errors_and_literal_categories(self):
        self.api()
        for value in ['NA', 'NaN', '.', '1_000', '1d3', ' ', 'inf']:
            with self.subTest(value=value):
                self.native(f'firm,year,x\n001,1,{value}\n'.encode(),
                            recipe(dict(op='ln', source='x', target='lx', invalid='missing')), succeeds=False)
        for raw, spec in [
            (b'firm,year,x\n001,1,0\n', recipe(dict(op='ln', source='x', target='lx', invalid='error'))),
            (b'firm,year,x\n001,1,1\n001,1,2\n', recipe()),
            (b'firm,year,x\n001,1.0000000000000001,1\n', recipe(dict(op='lag', source='x', target='lx', entity=['firm'], time='year', interval=1))),
            (b'firm,year,x,lx\n001,1,1,old\n', recipe(dict(op='ln', source='x', target='lx', invalid='error'))),
        ]:
            with self.subTest(raw=raw):
                self.native(raw, spec, succeeds=False)
        raw = b'firm,year,x\n001,1,\n002,2,\n'
        for spec in [recipe(dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='error')),
                     recipe(dict(op='filter', source='firm', operator='in', value=['none']),
                            dict(op='center', source='x', target='xc', by=[]),
                            dict(op='lag', source='x', target='xl', entity=['firm'], time='year', interval=1))]:
            expected, _ = self.api()[0](raw, spec)
            actual, _ = self.native(raw, spec)
            self.assertEqual(rows(actual), rows(expected))
        label = '中文 $macro `literal\' "quoted" \\ path\t'
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerows([['firm', 'year', 'group', 'x'], ['001', '1', label, '1'], ['002', '1', label, '3']])
        raw = stream.getvalue().encode()
        spec = recipe(dict(op='indicator', source='group', target='is_group', value=label, missing='zero'),
                      dict(op='winsor', source='x', target='xw', lower=.25, upper=.75, by=['group']))
        actual, audit = self.native(raw, spec)
        self.assertEqual([r['is_group'] for r in rows(actual)], ['1', '1'])
        self.assertEqual(audit['recipe'], spec)
        self.assertEqual(audit['steps'][1]['groups'][0]['group']['group'], label)

    @unittest.skipUnless(HAS_STATA, 'set ECONBIZ_TEST_STATA to opt into native Stata')
    def test_native_audit_fractional_json_and_stable_variance_scales(self):
        self.api()
        out, audit = self.native(b'firm,year,x\n001,1,0\n002,1,1\n', recipe(
            dict(op='winsor', source='x', target='w', lower=.25, upper=.75, by=[]),
            dict(op='center', source='x', target='c', by=[])))
        self.assertEqual(audit['steps'][0]['groups'][0]['lower_threshold'], .25)
        self.assertEqual(audit['steps'][1]['groups'][0]['mean'], .5)
        for raw, expected in [(b'firm,year,x\n001,1,-1e200\n002,1,-1\n003,1,1\n004,1,1e200\n', -math.sqrt(1.5)),
                              (b'firm,year,x\n001,1,1e-200\n002,1,2e-200\n', -1/math.sqrt(2))]:
            actual, audit = self.native(raw, recipe(dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='missing')))
            self.assertAlmostEqual(float(rows(actual)[0]['z']), expected)
            self.assertGreater(audit['steps'][0]['groups'][0]['sd'], 0)
        raw = b'firm,year,x\n001,1,-59.6260997496342\n002,1,-59.6260997496342\n003,1,-59.6260997496342\n'
        actual, audit = self.native(raw, recipe(dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='missing')))
        self.assertEqual([row['z'] for row in rows(actual)], ['', '', ''])
        self.assertEqual(audit['steps'][0]['groups'][0]['sd'], 0)
        raw = b'firm,year,x\n001,1,0.1\n002,1,0.2\n003,1,0.3\n'
        actual, _ = self.native(raw, recipe(dict(op='center', source='x', target='c', by=[]),
                                           dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='error')))
        self.assertEqual(rows(actual)[1]['c'], '0')
        self.assertEqual(rows(actual)[1]['z'], '0')

    @unittest.skipUnless(HAS_STATA, 'set ECONBIZ_TEST_STATA to opt into native Stata')
    def test_native_numeric_serialization_roundtrips_and_limits_derived_text_operations(self):
        prepare, _ = self.api()
        from econbiz.preprocessing_script import render_preparation_script
        for text in ['0.5', '1e20', '1e-200', '1e200', '-0.000001', '0.33333333333333331', '-0']:
            raw = f'firm,year,x,d\n001,1,{text},1\n'.encode()
            rule = dict(op='ratio', numerator='x', denominator='d', target='r', zero='error')
            expected, _ = prepare(raw, recipe(rule))
            actual, _ = self.native(raw, recipe(rule))
            self.assertEqual(rows(actual), rows(expected), text)
        raw = b'firm,year,x,d\n001,1,1,2\n'
        spec = recipe(dict(op='ratio', numerator='x', denominator='d', target='r', zero='error'),
                      dict(op='filter', source='r', operator='eq', value='0.5'))
        with self.assertRaises(WorkflowError):
            render_preparation_script(spec, backend='stata')
        for next_step in [dict(op='center', source='x', target='xc', by=['r']),
                          dict(op='indicator', source='r', target='dummy', value='0.5', missing='error'),
                          dict(op='lag', source='x', target='xl', entity=['r'], time='year', interval=1)]:
            with self.assertRaises(WorkflowError):
                render_preparation_script(recipe(spec['steps'][0], next_step), backend='stata')
        actual, _ = self.native(raw, recipe(spec['steps'][0], dict(op='filter', source='r', operator='ge', value=.5)))
        self.assertEqual(len(rows(actual)), 1)
        actual, _ = self.native(raw, recipe(dict(op='indicator', source='firm', target='dummy', value='001', missing='error'),
                                           dict(op='filter', source='dummy', operator='eq', value='1')))
        self.assertEqual(len(rows(actual)), 1)

    @unittest.skipUnless(HAS_STATA, 'set ECONBIZ_TEST_STATA to opt into native Stata')
    def test_native_rejects_invalid_utf8_in_untransformed_cells(self):
        self.api()
        self.native(b'firm,year,x,note\n001,1,1,\xff\n', recipe(), succeeds=False)


if __name__ == '__main__':
    unittest.main()
