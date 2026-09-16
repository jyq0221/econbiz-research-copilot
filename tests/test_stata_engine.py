"""Native Stata contracts. Opt in with ECONBIZ_TEST_STATA=/absolute/executable."""

import copy
import csv
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from econbiz.state import WorkflowError
from test_estimation import (NUMERICAL_DEPENDENCIES_AVAILABLE, panel,
                             specification, trusted_lsdv)

if NUMERICAL_DEPENDENCIES_AVAILABLE:
    import numpy as np
    from scipy import stats


class StataBundleTests(unittest.TestCase):
    def engine(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.stata_engine'),
                             'bounded Stata adapter is missing')
        return importlib.import_module('econbiz.stata_engine')

    @unittest.skipUnless(NUMERICAL_DEPENDENCIES_AVAILABLE, 'numerical test fixture requires optional dependencies')
    def test_bundle_is_deterministic_safe_and_preserves_unicode_source_mapping(self):
        rows, spec = panel(), specification()
        for row in rows:
            row['收入; exit 9'] = row.pop('y')
        spec['y'] = '收入; exit 9'
        engine = self.engine()
        bundle = engine.build_bundle(rows, spec)
        self.assertEqual(bundle, engine.build_bundle(rows, spec))
        self.assertTrue({'input.csv', 'mapping.json', 'analysis.do'} <= bundle.keys())
        self.assertTrue(all(Path(name).name == name and isinstance(data, bytes)
                            for name, data in bundle.items()))
        self.assertNotIn('收入'.encode(), bundle['analysis.do'])
        mapping = json.loads(bundle['mapping.json'])
        self.assertEqual(mapping['spec'], spec)
        self.assertEqual(mapping['sample_keys'][0], ['000', '2010'])
        csvrows = list(csv.DictReader(io.StringIO(bundle['input.csv'].decode())))
        self.assertEqual(len(csvrows), len(rows))
        self.assertEqual(csvrows[0]['rowid'], '1')

    @unittest.skipUnless(NUMERICAL_DEPENDENCIES_AVAILABLE, 'adapter requires optional numerical dependencies')
    def test_normalization_rejects_underflow_and_material_roundtrip_precision_loss(self):
        spec = specification((), 'classical', 'descriptive')
        spec['x'] = ['x']
        for values in (('1e-300', '1e300'), ('1e-300', '1e20'), ('1e-400', '1')):
            rows = [dict(firm=str(i), year='2020', x=value) for i, value in enumerate(values)]
            with self.subTest(values=values), self.assertRaises(WorkflowError):
                self.engine().build_bundle(rows, spec)
        for values in (('1e-150', '1e150'), ('0', '1e300')):
            rows = [dict(firm=str(i), year='2020', x=value) for i, value in enumerate(values)]
            with self.subTest(values=values):
                bundle = self.engine().build_bundle(rows, spec)
                data = list(csv.DictReader(io.StringIO(bundle['input.csv'].decode())))
                scale = json.loads(bundle['mapping.json'])['scales'][0]
                for row, value in zip(data, values):
                    self.assertTrue(np.isclose(float(row['n1'])*scale, float(value), rtol=3e-15, atol=0))

    @unittest.skipUnless(NUMERICAL_DEPENDENCIES_AVAILABLE, 'adapter requires optional numerical dependencies')
    def test_unscale_preserves_expressible_outputs_without_intermediate_underflow_or_overflow(self):
        unscale = self.engine()._unscale
        for value, multipliers, divisors, expected in (
            (1e-200, (1e300,), (1e-100,), 1e200),
            (1e200, (1e-300,), (1e100,), 1e-200),
            (1e-100, (1e200, 1e200), (), 1e300),
            (1e100, (1e-200, 1e-200), (), 1e-300),
            (0.0, (1e300, 1e300), (), 0.0),
        ):
            with self.subTest(value=value, multipliers=multipliers):
                actual = unscale(value, *multipliers, divisors=divisors)
                self.assertTrue(np.isclose(actual, expected, rtol=3e-15, atol=0))
        for value, multipliers in ((1.0, (1e-200, 1e-200)),
                                   (1.0, (1e200, 1e200)), (.3, (1e-323,))):
            with self.subTest(value=value, multipliers=multipliers), self.assertRaises(WorkflowError):
                unscale(value, *multipliers)

    @unittest.skipUnless(NUMERICAL_DEPENDENCIES_AVAILABLE, 'adapter requires optional numerical dependencies')
    def test_distinct_safe_run_tokens_bind_the_frozen_bundle(self):
        engine = self.engine()
        rows, spec = panel(), specification()
        first = engine.build_bundle(rows, spec, run_token='run_A-123')
        second = engine.build_bundle(rows, spec, run_token='run_B-456')
        self.assertEqual(first['input.csv'], second['input.csv'])
        self.assertNotEqual(first['mapping.json'], second['mapping.json'])
        self.assertNotEqual(first['analysis.do'], second['analysis.do'])
        self.assertEqual(json.loads(first['mapping.json'])['run_token'], 'run_A-123')
        for token in ('', 'contains space', 'bad";exit', 'bad\n', '中文', 'x'*129, None, 12):
            with self.subTest(token=token), self.assertRaises(WorkflowError):
                engine.build_bundle(rows, spec, run_token=token)


@unittest.skipUnless(os.environ.get('ECONBIZ_TEST_STATA') and NUMERICAL_DEPENDENCIES_AVAILABLE,
                     'real Stata tests require explicit ECONBIZ_TEST_STATA and optional analysis dependencies')
class StataNativeTests(StataBundleTests):
    @classmethod
    def setUpClass(cls):
        from econbiz.stata_runtime import probe_stata
        cls.runtime = probe_stata(os.environ['ECONBIZ_TEST_STATA'])

    def run_native(self, rows, spec, *, run_token='standalone'):
        engine = self.engine()
        temp = tempfile.TemporaryDirectory(prefix='econbiz_stata_中文_')
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        bundle = root/'bundle'
        bundle.mkdir()
        for name, data in engine.build_bundle(rows, spec, run_token=run_token).items():
            (bundle/name).write_bytes(data)
        result = engine.run_estimation(rows, spec, bundle, root/'out', self.runtime, run_token=run_token)
        return result, root/'out'/'native'

    def test_all_eighteen_fe_and_covariance_cases_match_explicit_lsdv(self):
        for unbalanced in (False, True):
            for effects in (('entity',), ('time',), ('entity', 'time')):
                for method in ('classical', 'hc1', 'cluster'):
                    with self.subTest(unbalanced=unbalanced, effects=effects, method=method):
                        rows, spec = panel(unbalanced), specification(effects, method)
                        result, native = self.run_native(rows, spec)
                        coef, errors, df, inference_df = trusted_lsdv(rows, spec)
                        np.testing.assert_allclose([p['coefficient'] for p in result['parameters']], coef, rtol=1e-9, atol=1e-10)
                        np.testing.assert_allclose([p['std_error'] for p in result['parameters']], errors, rtol=1e-9, atol=1e-10)
                        self.assertEqual(result['df_resid'], df)
                        self.assertEqual(result['inference_df'], inference_df)
                        self.assertEqual(result['rank'], len(rows)-df)
                        self.assertEqual(result['actual_spec'], spec)
                        self.assertEqual(result['sample_keys'], [[r['firm'], r['year']] for r in rows])
                        for j, parameter in enumerate(result['parameters']):
                            self.assertAlmostEqual(parameter['p_value'], 2*stats.t.sf(abs(coef[j]/errors[j]), inference_df), places=10)
                            self.assertAlmostEqual(parameter['ci_low'], coef[j]-stats.t.ppf(.975, inference_df)*errors[j], places=10)
                        covariance = np.asarray(result['covariance_matrix'])
                        np.testing.assert_allclose(np.diag(covariance), errors**2, rtol=1e-9)
                        self.assertEqual(result, self.engine().read_result(rows, spec, native))
                        from econbiz.numerical_check import verify_numerics
                        self.assertEqual(verify_numerics(rows, spec, result, backend='stata')['check_status'], 'passed')

    def test_descriptive_linear_quantiles_and_single_observation(self):
        rows = [dict(firm=str(i), year='2020', x=str(x), z=str(-x))
                for i, x in enumerate([0, 2, 4, 10])]
        spec = specification((), 'classical', 'descriptive')
        for sample in (rows, rows[:1]):
            result, _ = self.run_native(sample, spec)
            self.assertEqual(result['covariance_matrix'], [])
            self.assertEqual(result['diagnostics']['engine'], 'stata.descriptive')
            values = np.array([float(r['x']) for r in sample])
            summary = result['descriptive']['x']
            self.assertAlmostEqual(summary['p25'], np.quantile(values, .25))
            self.assertAlmostEqual(summary['p75'], np.quantile(values, .75))
            if len(sample) == 1:
                self.assertIsNone(summary['std'])
            else:
                self.assertAlmostEqual(summary['std'], values.std(ddof=1))

    def test_singletons_reordered_effects_custom_cluster_and_scaled_unicode_fields(self):
        rows, spec = panel(True, True), specification()
        spec['fixed_effects'].reverse()
        spec['standard_errors']['field'] = '聚类$";'
        for row in rows:
            row[spec['standard_errors']['field']] = str(int(row['firm']) % 3)
            row['收入$";'] = str(float(row.pop('y'))*1e60)
            row['投入;'] = str(float(row.pop('x'))*1e50)
        spec['y'], spec['x'][0] = '收入$";', '投入;'
        result, _ = self.run_native(rows, spec)
        ordinary = copy.deepcopy(rows)
        for row in ordinary:
            row[spec['y']] = str(float(row[spec['y']])/1e60)
            row[spec['x'][0]] = str(float(row[spec['x'][0]])/1e50)
        coef, errors, _, _ = trusted_lsdv(ordinary, spec)
        factors = np.array([1e10, 1e60])
        np.testing.assert_allclose([p['coefficient'] for p in result['parameters']], coef*factors, rtol=1e-9)
        np.testing.assert_allclose([p['std_error'] for p in result['parameters']], errors*factors, rtol=1e-9)
        self.assertEqual(result['diagnostics']['singleton_entity_count'], 1)
        self.assertTrue(result['warnings'])

    def test_rejects_absorbed_collinear_zero_residual_and_invalid_degrees(self):
        for case in ('absorbed', 'collinear', 'zero_residual', 'df', 'one_cluster', 'disconnected'):
            rows, spec = panel(), specification()
            if case == 'absorbed':
                for row in rows:
                    row['x'] = row['firm']
            elif case == 'collinear':
                for row in rows:
                    row['z'] = row['x']
            elif case == 'zero_residual':
                for row in rows:
                    row['y'] = str(2*float(row['x'])-float(row['z']))
            elif case == 'df':
                rows = rows[:3]
                spec = specification(('entity',), 'classical')
            elif case == 'one_cluster':
                for row in rows:
                    row['group'] = 'one'
                spec['standard_errors']['field'] = 'group'
            else:
                rows = [r for r in rows if (int(r['firm']) < 3) == (int(r['year']) < 2013)]
            with self.subTest(case=case), self.assertRaises(WorkflowError):
                self.run_native(rows, spec)

    def test_native_tampering_in_values_sample_covariance_and_metadata_is_rejected(self):
        rows, spec = panel(True), specification()
        _, native = self.run_native(rows, spec)
        engine = self.engine()
        for filename in ('roundtrip.csv', 'covariance.csv', 'metadata.json', 'coefficients.csv', 'table.csv'):
            path = native/filename
            original = path.read_bytes()
            with self.subTest(filename=filename):
                path.write_bytes(b'corrupt\n')
                with self.assertRaises(WorkflowError):
                    engine.read_result(rows, spec, native)
                path.write_bytes(original)
        path = native/'roundtrip.csv'
        original = path.read_text()
        parsed = list(csv.reader(io.StringIO(original)))
        sample_index = parsed[0].index('sample')
        parsed[1][sample_index] = '0'
        buffer = io.StringIO()
        csv.writer(buffer).writerows(parsed)
        path.write_text(buffer.getvalue())
        with self.assertRaises(WorkflowError):
            engine.read_result(rows, spec, native)
        path.write_text(original)
        for field in ('rowid', 'ec', 'tc', 'cc', 'n1'):
            parsed = list(csv.reader(io.StringIO(original)))
            index = parsed[0].index(field)
            parsed[1][index] = repr(float(parsed[1][index])+.25)
            buffer = io.StringIO()
            csv.writer(buffer).writerows(parsed)
            path.write_text(buffer.getvalue())
            with self.subTest(field=field), self.assertRaises(WorkflowError):
                engine.read_result(rows, spec, native)
            path.write_text(original)
        path = native/'metadata.json'
        original = path.read_text()
        for field, value in [('cmdline', 'regress n3 n1 n2'), ('absvar', 'tc'),
                             ('cluster_count', 100), ('absorbed_df', 1), ('rss', -1)]:
            changed = json.loads(original)
            changed[field] = value
            path.write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaises(WorkflowError):
                engine.read_result(rows, spec, native)
            path.write_text(original)
        for filename, cell in [('coefficients.csv', (0, 0)), ('core_covariance.csv', (0, 1)),
                               ('covariance.csv', (0, 0)), ('table.csv', (3, 0))]:
            path = native/filename
            original = path.read_text()
            parsed = list(csv.reader(io.StringIO(original)))
            i, j = cell
            parsed[i][j] = repr(float(parsed[i][j])+.25)
            buffer = io.StringIO()
            csv.writer(buffer).writerows(parsed)
            path.write_text(buffer.getvalue())
            with self.subTest(filename=filename), self.assertRaises(WorkflowError):
                engine.read_result(rows, spec, native)
            path.write_text(original)

    def test_rejects_nearly_absorbed_regressor(self):
        rows, spec = panel(), specification(('entity',), 'classical')
        for row in rows:
            row['x'] = str(int(row['firm'])+1e-11*float(row['x']))
        with self.assertRaises(WorkflowError):
            self.run_native(rows, spec)

    def test_native_evidence_rejects_symlinks_and_missing_log(self):
        rows, spec = panel(True), specification()
        _, native = self.run_native(rows, spec)
        engine = self.engine()
        log = native/'analysis.log'
        original_log = log.read_bytes()
        log.unlink()
        with self.subTest(case='missing log'), self.assertRaises(WorkflowError):
            engine.read_result(rows, spec, native)
        log.write_bytes(original_log)
        for path in sorted(native.iterdir()):
            if not path.is_file():
                continue
            original = path.read_bytes()
            external = native.parent/('external_'+path.name)
            external.write_bytes(original)
            path.unlink()
            path.symlink_to(external)
            with self.subTest(file=path.name), self.assertRaises(WorkflowError):
                engine.read_result(rows, spec, native)
            path.unlink()
            path.write_bytes(original)
        alias = native.parent/'native_alias'
        alias.symlink_to(native, target_is_directory=True)
        with self.subTest(case='native directory symlink'), self.assertRaises(WorkflowError):
            engine.read_result(rows, spec, alias)

    def test_nonzero_native_covariance_and_rss_cannot_unscale_to_zero(self):
        for yscale, xscale in ((1e-170, 1), (1e-308, 1), (1e-170, 1e-170)):
            rows, spec = panel(True), specification()
            for row in rows:
                row['y'] = str(float(row['y'])*yscale)
                for name in spec['x']:
                    row[name] = str(float(row[name])*xscale)
            with self.subTest(yscale=yscale, xscale=xscale), self.assertRaises(WorkflowError):
                self.run_native(rows, spec)

    def test_wrong_shape_native_metadata_raises_workflow_error(self):
        rows, spec = panel(True), specification()
        _, native = self.run_native(rows, spec)
        metadata = native/'metadata.json'
        original = metadata.read_bytes()
        for value in ([], None, 'metadata', True, 42):
            metadata.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(WorkflowError):
                self.engine().read_result(rows, spec, native)
        metadata.write_bytes(original)

    def test_old_native_outputs_cannot_satisfy_a_new_run_with_identical_inputs(self):
        engine = self.engine()
        rows, spec = panel(True), specification()
        _, previous = self.run_native(rows, spec, run_token='old_run_123')
        self.assertEqual(json.loads((previous/'metadata.json').read_text())['run_token'], 'old_run_123')
        self.assertEqual((previous/'complete.txt').read_text().strip(), 'completed:old_run_123')
        new = previous.parent/'new_native'
        new.mkdir()
        for path in previous.iterdir():
            (new/path.name).write_bytes(path.read_bytes())
        for name, data in engine.build_bundle(rows, spec, run_token='new_run_456').items():
            (new/name).write_bytes(data)
        with self.subTest(case='all previous outputs'), self.assertRaises(WorkflowError):
            engine.read_result(rows, spec, new, run_token='new_run_456')
        (new/'complete.txt').write_text('completed:new_run_456\n')
        with self.subTest(case='only completion token current'), self.assertRaises(WorkflowError):
            engine.read_result(rows, spec, new, run_token='new_run_456')
        metadata = json.loads((new/'metadata.json').read_text())
        metadata['run_token'] = 'new_run_456'
        (new/'metadata.json').write_text(json.dumps(metadata))
        (new/'complete.txt').write_text('completed:old_run_123\n')
        with self.subTest(case='only metadata token current'), self.assertRaises(WorkflowError):
            engine.read_result(rows, spec, new, run_token='new_run_456')

    def test_native_regress_with_explicit_dummies_matches_areg(self):
        from econbiz.stata_runtime import run_stata
        for method in ('classical', 'hc1', 'cluster'):
            rows, spec = panel(True, True), specification(method=method)
            _, native = self.run_native(rows, spec)
            option = {'classical': '', 'hc1': ', vce(robust)', 'cluster': ', vce(cluster cc)'}[method]
            script = '\n'.join(['version 19.0', 'clear all', 'set more off', 'global S_ADO "BASE"',
                'import delimited "input.csv", clear asdouble', 'do "helpers.mata"',
                'regress n3 n1 n2 i.ec i.tc'+option,
                'matrix oracle_b = e(b)', 'matrix oracle_V = e(V)',
                'mata: eb_matrix("oracle_b.csv", st_matrix("oracle_b")[|1,1\\1,2|])',
                'mata: eb_matrix("oracle_V.csv", st_matrix("oracle_V")[|1,1\\2,2|])',
                'exit, clear'])+'\n'
            oracle = native/'oracle.do'
            oracle.write_text(script)
            completed = run_stata(self.runtime, oracle, native)
            self.assertEqual(completed.returncode, 0)
            np.testing.assert_allclose(np.loadtxt(native/'oracle_b.csv', delimiter=','),
                                       np.loadtxt(native/'coefficients.csv', delimiter=',')[:2], rtol=1e-10)
            np.testing.assert_allclose(np.loadtxt(native/'oracle_V.csv', delimiter=','),
                                       np.loadtxt(native/'core_covariance.csv', delimiter=','), rtol=1e-10)

    def test_stata_does_not_call_python_estimate_or_reference(self):
        with patch('econbiz.estimation.estimate', side_effect=AssertionError('Python primary called')), \
             patch('econbiz.numerical_check._reference', side_effect=AssertionError('Python reference called')):
            result, _ = self.run_native(panel(), specification())
        self.assertEqual(result['diagnostics']['engine'], 'stata.areg')
