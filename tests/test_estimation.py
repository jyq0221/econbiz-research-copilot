"""Numerical contracts against LSDV; optional analysis deps plus statsmodels needed.

statsmodels is a linearmodels dependency; tests additionally use its LSDV OLS as
a third numerical reference. Production verification uses neither OLS engine.
"""

import copy
import importlib
import importlib.util
import json
import unittest
from unittest.mock import patch

try:
    import numpy as np
    import pandas as pd
    import scipy.stats
    import linearmodels
    import statsmodels.api as sm
    from statsmodels.stats.sandwich_covariance import cov_cluster
    NUMERICAL_DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:
    NUMERICAL_DEPENDENCIES_AVAILABLE = False

from econbiz.state import WorkflowError


def specification(effects=('entity', 'time'), method='cluster', model='linear_fe'):
    return dict(model=model, y='y' if model == 'linear_fe' else None,
                x=['x', 'z'], fixed_effects=[{'entity': 'firm', 'time': 'year'}[e] for e in effects], entity='firm', time='year',
                standard_errors=dict(method=method, field='firm' if method == 'cluster' else None,
                                     rationale='Pre-specified inference'), confidence=0.95)


def panel(unbalanced=False, singleton=False):
    rng = np.random.default_rng(4821)
    rows = []
    for i in range(7):
        for t in range(6):
            if unbalanced and (i, t) in {(0, 0), (2, 4), (4, 1), (6, 5)}:
                continue
            x, z, noise = rng.normal(size=3)
            y = 1.7*x - 0.6*z + i*0.4 + t*0.3 + noise*(0.4+i*0.1)
            rows.append(dict(firm=f'{i:03}', year=str(2010+t), x=str(x), z=str(z), y=str(y)))
    if singleton:
        rows.append(dict(firm='007', year='2012', x='1.2', z='-1.1', y='8.1'))
    return rows


def trusted_lsdv(rows, spec):
    frame = pd.DataFrame(rows)
    x = frame[spec['x']].astype(float).to_numpy()
    dummies = []
    for effect in spec['fixed_effects']:
        key = effect
        dummies.append(pd.get_dummies(frame[key], drop_first=bool(dummies), dtype=float).to_numpy())
    design = np.column_stack([x] + dummies)
    fitted = sm.OLS(frame[spec['y']].astype(float), design).fit()
    method = spec['standard_errors']['method']
    if method == 'classical':
        covariance = fitted.cov_params().to_numpy()
    elif method == 'hc1':
        covariance = fitted.get_robustcov_results(cov_type='HC1').cov_params()
    else:
        covariance = cov_cluster(fitted, frame[spec['standard_errors']['field']], use_correction=True)
    p = len(spec['x'])
    df = frame[spec['standard_errors']['field']].nunique()-1 if method == 'cluster' else fitted.df_resid
    return fitted.params.to_numpy()[:p], np.sqrt(np.diag(covariance))[:p], int(fitted.df_resid), int(df)


@unittest.skipUnless(NUMERICAL_DEPENDENCIES_AVAILABLE, 'optional analysis dependencies and test-only statsmodels required')
class EstimationTests(unittest.TestCase):
    def estimate(self, rows, spec):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.estimation'), 'estimation module is missing')
        return importlib.import_module('econbiz.estimation').estimate(rows, spec)

    def verify(self, rows, spec, result):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.numerical_check'), 'independent numerical checker is missing')
        return importlib.import_module('econbiz.numerical_check').verify_numerics(rows, spec, result)

    def test_public_fixed_effects_use_actual_field_names_and_preserve_spec(self):
        rows, spec = panel(True), specification()
        spec['fixed_effects'] = ['firm', 'year']
        result = self.estimate(rows, spec)
        self.assertEqual(result['actual_spec']['fixed_effects'], ['firm', 'year'])
        self.assertEqual(self.verify(rows, spec, result)['check_status'], 'passed')

    def test_one_and_two_way_balanced_unbalanced_match_lsdv_for_every_covariance(self):
        for unbalanced in (False, True):
            for effects in (('entity',), ('time',), ('entity', 'time')):
                for method in ('classical', 'hc1', 'cluster'):
                    with self.subTest(unbalanced=unbalanced, effects=effects, method=method):
                        rows, spec = panel(unbalanced), specification(effects, method)
                        result = self.estimate(rows, spec)
                        coef, se, df, inference_df = trusted_lsdv(rows, spec)
                        np.testing.assert_allclose([p['coefficient'] for p in result['parameters']], coef, rtol=1e-9, atol=1e-10)
                        np.testing.assert_allclose([p['std_error'] for p in result['parameters']], se, rtol=1e-9, atol=1e-10)
                        self.assertEqual(result['df_resid'], df)
                        self.assertEqual(result['inference_df'], inference_df)
                        for i, parameter in enumerate(result['parameters']):
                            pval = 2*scipy.stats.t.sf(abs(coef[i]/se[i]), inference_df)
                            critical = scipy.stats.t.ppf(.975, inference_df)
                            self.assertAlmostEqual(parameter['p_value'], pval, places=11)
                            self.assertAlmostEqual(parameter['ci_low'], coef[i]-critical*se[i], places=10)
                            self.assertAlmostEqual(parameter['ci_high'], coef[i]+critical*se[i], places=10)
                        self.assertEqual(result['actual_spec'], spec)
                        self.assertEqual(result['sample_keys'], [[r['firm'], r['year']] for r in rows])
                        self.assertEqual(result['rank'], len(rows)-df)
                        json.dumps(result, allow_nan=False)
                        self.assertEqual(self.verify(rows, spec, result)['check_status'], 'passed')

    def test_known_analytical_slope(self):
        rows = [dict(firm=str(i), year=str(2010+t), x=str(t-1),
                     y=str(i+1.75*(t-1)+[1, -2, 1][t]*(i+1)*.1))
                for i in range(4) for t in range(3)]
        spec = specification(('entity',), 'classical')
        spec['x'] = ['x']
        result = self.estimate(rows, spec)
        self.assertAlmostEqual(result['parameters'][0]['coefficient'], 1.75, places=12)
        self.assertEqual(self.verify(rows, spec, result)['check_status'], 'passed')

    def test_singletons_are_retained_and_explicit(self):
        rows, spec = panel(True, True), specification()
        result = self.estimate(rows, spec)
        self.assertEqual(result['nobs'], len(rows))
        self.assertEqual(result['diagnostics']['singleton_entity_count'], 1)
        self.assertTrue(result['warnings'])
        coef, se, _, _ = trusted_lsdv(rows, spec)
        np.testing.assert_allclose([p['coefficient'] for p in result['parameters']], coef, rtol=1e-9)
        np.testing.assert_allclose([p['std_error'] for p in result['parameters']], se, rtol=1e-9)
        self.assertEqual(self.verify(rows, spec, result)['check_status'], 'passed')

    def test_descriptive_result_and_independent_check(self):
        rows = panel(True)
        spec = specification((), 'classical', 'descriptive')
        result = self.estimate(rows, spec)
        self.assertEqual(result['parameters'], [])
        self.assertIsNone(result['rank'])
        for key in spec['x']:
            values = np.array([float(r[key]) for r in rows])
            summary = result['descriptive'][key]
            self.assertEqual(summary['count'], len(rows))
            self.assertAlmostEqual(summary['mean'], values.mean(), places=13)
            self.assertAlmostEqual(summary['std'], values.std(ddof=1), places=13)
            self.assertAlmostEqual(summary['p25'], np.quantile(values, .25), places=13)
        self.assertEqual(self.verify(rows, spec, result)['check_status'], 'passed')
        only = self.estimate(rows[:1], spec)
        self.assertIsNone(only['descriptive']['x']['std'])
        json.dumps(only, allow_nan=False)

    def test_regression_includes_same_sample_summaries_in_original_units(self):
        rows, spec = panel(True, True), specification()
        for row in rows:
            row['x'] = str(float(row['x'])*1e6)
            row['y'] = str(float(row['y'])*1e4)
        result = self.estimate(rows, spec)
        report = self.verify(rows, spec, result)
        self.assertEqual(report['check_status'], 'passed')
        numeric_fields = spec['x']+[spec['y']]
        for estimate in (result, report['reference']):
            self.assertEqual(list(estimate['descriptive']), numeric_fields)
            for field in numeric_fields:
                values = np.array([float(row[field]) for row in rows])
                summary = estimate['descriptive'][field]
                self.assertEqual(summary['count'], result['nobs'])
                self.assertAlmostEqual(summary['mean'], values.mean(), delta=1e-8)
                self.assertAlmostEqual(summary['std'], values.std(ddof=1), delta=1e-8)
                self.assertEqual(summary['min'], values.min())
                self.assertEqual(summary['max'], values.max())
        result['descriptive']['y']['mean'] += 100
        changed = self.verify(rows, spec, result)
        self.assertEqual(changed['check_status'], 'failed')
        check = next(c for c in changed['checks'] if c['name'] == 'descriptive.y.mean')
        self.assertGreater(check['delta'], check['tolerance'])

    def test_verifier_does_not_call_primary_and_detects_tampering(self):
        rows, spec = panel(True), specification()
        result = self.estimate(rows, spec)
        with patch('econbiz.estimation.estimate', side_effect=AssertionError('Primary called by checker')):
            self.assertEqual(self.verify(rows, spec, result)['check_status'], 'passed')
        mutations = [
            lambda r: r['parameters'][0].update(coefficient=r['parameters'][0]['coefficient']+.001),
            lambda r: r['parameters'][0].update(std_error=r['parameters'][0]['std_error']*.5),
            lambda r: r['parameters'][0].update(p_value=.9),
            lambda r: r['parameters'][0].update(ci_high=999),
            lambda r: r['parameters'][0].update(term='other'),
            lambda r: r['sample_keys'].reverse(),
            lambda r: r.update(nobs=r['nobs']+1),
            lambda r: r.update(rank=r['rank']+1),
            lambda r: r.update(df_resid=r['df_resid']+1),
            lambda r: r.update(inference_df=r['inference_df']+1),
            lambda r: r['actual_spec']['standard_errors'].update(method='hc1'),
            lambda r: r['parameters'][0].update(coefficient=float('nan')),
            lambda r: r.pop('parameters'),
        ]
        for mutate in mutations:
            candidate = copy.deepcopy(result)
            mutate(candidate)
            with self.subTest(result=candidate):
                report = self.verify(rows, spec, candidate)
                self.assertEqual(report['check_status'], 'failed')
                json.dumps(report, allow_nan=False)
        self.assertEqual(self.verify(rows, spec, None)['check_status'], 'failed')
        descriptive_spec = specification((), 'classical', 'descriptive')
        descriptive = self.estimate(rows, descriptive_spec)
        descriptive['descriptive']['x']['mean'] += .01
        self.assertEqual(self.verify(rows, descriptive_spec, descriptive)['check_status'], 'failed')

    def test_scaled_data_remains_accurate_and_finite(self):
        rows, spec = panel(True), specification()
        for row in rows:
            row['x'] = str(float(row['x'])*1e12)
            row['z'] = str(float(row['z'])*1e-10)
            row['y'] = str(float(row['y'])*1e8)
        result = self.estimate(rows, spec)
        self.assertEqual(self.verify(rows, spec, result)['check_status'], 'passed')
        json.dumps(result, allow_nan=False)

    def test_time_and_custom_clusters_reversed_effects_and_singleton_time(self):
        rows = panel(True)
        rows.append(dict(firm='003', year='2020', x='-2.1', z='1.5', y='2.9'))
        for row in rows:
            row['region'] = str(int(row['firm']) % 3)
        for field in ('year', 'region'):
            with self.subTest(cluster=field):
                spec = specification(('time', 'entity'))
                spec['standard_errors']['field'] = field
                result = self.estimate(rows, spec)
                coef, se, _, df = trusted_lsdv(rows, spec)
                np.testing.assert_allclose([p['coefficient'] for p in result['parameters']], coef, rtol=1e-9)
                np.testing.assert_allclose([p['std_error'] for p in result['parameters']], se, rtol=1e-9)
                self.assertEqual(result['inference_df'], df)
                self.assertEqual(result['diagnostics']['singleton_time_count'], 1)
                self.assertEqual(self.verify(rows, spec, result)['check_status'], 'passed')

    def test_missing_contract_fields_extra_nonfinite_and_warning_tamper_fail(self):
        rows, spec = panel(True), specification((), 'classical', 'descriptive')
        result = self.estimate(rows, spec)
        candidates = []
        for key in ('df_resid', 'rank', 'inference_df', 'warnings', 'diagnostics'):
            candidate = copy.deepcopy(result)
            candidate.pop(key)
            candidates.append(candidate)
        candidate = copy.deepcopy(result)
        candidate['unexpected'] = float('nan')
        candidates.append(candidate)
        candidate = copy.deepcopy(result)
        candidate['warnings'] = ['altered']
        candidates.append(candidate)
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertEqual(self.verify(rows, spec, candidate)['check_status'], 'failed')

    def test_reference_nonconvergence_fails_without_exposing_a_reference(self):
        rows, spec = panel(True), specification()
        result = self.estimate(rows, spec)
        import econbiz.numerical_check as checker
        original = checker.lsmr
        def unconverged(*args, **kwargs):
            output = list(original(*args, **kwargs))
            output[1] = 7
            return tuple(output)
        with patch.object(checker, 'lsmr', side_effect=unconverged):
            report = self.verify(rows, spec, result)
        self.assertEqual(report['check_status'], 'failed')
        self.assertIsNone(report['reference'])

    def test_near_collinearity_and_bounded_projection_are_rejected(self):
        rows, spec = panel(True), specification()
        for i, row in enumerate(rows):
            row['z'] = str(float(row['x'])+1e-10*((i % 3)-1))
        with self.assertRaises(WorkflowError):
            self.estimate(rows, spec)
        with patch('econbiz.estimation._MAX_DUMMY_CELLS', 10):
            with self.assertRaises(WorkflowError):
                self.estimate(panel(), specification())

    def test_independent_checker_rejects_unsupported_spec_even_with_matching_metadata(self):
        rows, spec = panel(True), specification()
        result = self.estimate(rows, spec)
        cases = []
        for key, value in [('rationale', ''), ('weights', 'weight'), ('method', 'unrecognized')]:
            changed = copy.deepcopy(spec)
            changed['standard_errors'][key] = value
            cases.append(changed)
        for changed in cases:
            candidate = copy.deepcopy(result)
            candidate['actual_spec'] = changed
            with self.subTest(spec=changed):
                self.assertEqual(self.verify(rows, changed, candidate)['check_status'], 'failed')

    def test_unrepresentable_descriptive_output_raises_workflow_error(self):
        rows = [dict(firm='a', year='2010', x='1.7e308'), dict(firm='a', year='2011', x='-1.7e308')]
        spec = specification((), 'classical', 'descriptive')
        spec['x'] = ['x']
        with self.assertRaises(WorkflowError):
            self.estimate(rows, spec)

    def test_malformed_large_numeric_and_extra_diagnostics_fail_without_exception(self):
        rows, spec = panel(True), specification()
        result = self.estimate(rows, spec)
        candidate = copy.deepcopy(result)
        candidate['parameters'][0]['coefficient'] = 10**1000
        self.assertEqual(self.verify(rows, spec, candidate)['check_status'], 'failed')
        candidate = copy.deepcopy(result)
        candidate['diagnostics']['weights'] = 'unexpected'
        self.assertEqual(self.verify(rows, spec, candidate)['check_status'], 'failed')

    def test_check_report_exposes_numeric_deviation_and_fixed_tolerance(self):
        rows, spec = panel(True), specification()
        result = self.estimate(rows, spec)
        result['parameters'][0]['coefficient'] += .01
        report = self.verify(rows, spec, result)
        check = next(c for c in report['checks'] if c['name'] == 'parameters[0].coefficient')
        self.assertFalse(check['passed'])
        self.assertEqual(check['actual'], result['parameters'][0]['coefficient'])
        self.assertAlmostEqual(check['delta'], abs(check['actual']-check['reference']), places=14)
        self.assertEqual(check['tolerance'], 1e-8+1e-6*abs(check['reference']))

    def test_descriptive_checker_checks_declared_cluster_field(self):
        rows, spec = panel(True), specification((), 'classical', 'descriptive')
        result = self.estimate(rows, spec)
        spec['standard_errors'].update(method='cluster', field='missing_cluster')
        result['actual_spec'] = copy.deepcopy(spec)
        with self.assertRaises(WorkflowError):
            self.estimate(rows, spec)
        self.assertEqual(self.verify(rows, spec, result)['check_status'], 'failed')

    def test_invalid_or_unidentified_models_are_rejected(self):
        cases = []
        rows, spec = panel(), specification()
        for bad in ('NaN', 'inf', '-inf', 'unknown'):
            r = copy.deepcopy(rows)
            r[0]['x'] = bad
            cases.append((r, spec, 'nonfinite/nonnumeric'))
        r = copy.deepcopy(rows)
        for row in r:
            row['x'] = str(int(row['firm']))
        cases.append((r, spec, 'absorbed'))
        r = copy.deepcopy(rows)
        for row in r:
            row['z'] = str(2*float(row['x']))
        cases.append((r, spec, 'collinear'))
        r = copy.deepcopy(rows)
        for row in r:
            row['constant'] = '1'
        s = copy.deepcopy(spec)
        s['x'] = ['constant']
        cases.append((r, s, 'constant absorbed'))
        r = copy.deepcopy(rows)
        for row in r:
            row['cluster'] = 'only'
        s = copy.deepcopy(spec)
        s['standard_errors']['field'] = 'cluster'
        cases.append((r, s, 'one cluster'))
        r = copy.deepcopy(rows)
        for row in r:
            if int(row['firm']) >= 3:
                row['year'] = str(int(row['year'])+100)
        cases.append((r, spec, 'disconnected two way'))
        r = copy.deepcopy(rows)
        for row in r:
            row['y'] = str(2*float(row['x'])+int(row['firm']))
        cases.append((r, spec, 'zero residual variance'))
        for key, value in [('model', 'logit'), ('fixed_effects', ['other']), ('confidence', .9), ('x', ['x','x'])]:
            s = copy.deepcopy(spec)
            s[key] = value
            cases.append((rows, s, key))
        cases.extend([(rows[:3], spec, 'nonpositive df'), (rows+[rows[0]], spec, 'duplicate keys'), ([], spec, 'empty')])
        for r, s, name in cases:
            with self.subTest(name=name):
                with self.assertRaises(WorkflowError):
                    self.estimate(r, s)


if __name__ == '__main__':
    unittest.main()
