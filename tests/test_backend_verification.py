import copy
import inspect
import unittest
from unittest.mock import patch

import test_estimation as fixtures


@unittest.skipUnless(fixtures.NUMERICAL_DEPENDENCIES_AVAILABLE, 'analysis dependencies required')
class BackendVerificationTests(unittest.TestCase):
    def api(self):
        from econbiz.numerical_check import verify_numerics
        self.assertIn('backend', inspect.signature(verify_numerics).parameters,
                      'verification must bind to frozen backend selection')
        return verify_numerics

    def stata_shaped_reference(self):
        from econbiz.estimation import estimate
        rows, spec = fixtures.panel(True), fixtures.specification()
        result = estimate(rows, spec)
        frame = fixtures.pd.DataFrame(rows)
        design = fixtures.np.column_stack([frame[spec['x']].astype(float).to_numpy(),
            fixtures.pd.get_dummies(frame.firm, dtype=float).to_numpy(),
            fixtures.pd.get_dummies(frame.year, drop_first=True, dtype=float).to_numpy()])
        fit = fixtures.sm.OLS(frame.y.astype(float), design).fit()
        result['covariance_matrix'] = fixtures.cov_cluster(fit, frame.firm, use_correction=True)[:2, :2].tolist()
        for key in ('scaled_condition_number', 'auto_df', 'count_effects', 'debiased', 'group_debias'):
            result['diagnostics'].pop(key)
        result['diagnostics']['engine'] = 'stata.areg'
        return rows, spec, result

    def test_stata_contract_checks_full_core_covariance_independently(self):
        verify = self.api()
        rows, spec, result = self.stata_shaped_reference()
        with patch('econbiz.estimation.estimate', side_effect=AssertionError('primary must not run')):
            self.assertEqual(verify(rows, spec, result, backend='stata')['check_status'], 'passed')
        result['covariance_matrix'][0][1] += .01
        self.assertEqual(verify(rows, spec, result, backend='stata')['check_status'], 'failed')

    def test_backend_cannot_be_inferred_from_self_reported_engine(self):
        verify = self.api()
        rows, spec, result = self.stata_shaped_reference()
        self.assertEqual(verify(rows, spec, result)['check_status'], 'failed')
        result['diagnostics']['engine'] = 'linearmodels.PanelOLS'
        self.assertEqual(verify(rows, spec, result, backend='stata')['check_status'], 'failed')
        self.assertEqual(verify(rows, spec, result, backend='auto')['check_status'], 'failed')

    def test_python_legacy_contract_stays_unchanged(self):
        verify = self.api()
        from econbiz.estimation import estimate
        rows, spec = fixtures.panel(), fixtures.specification()
        result = estimate(rows, spec)
        self.assertNotIn('covariance_matrix', result)
        self.assertEqual(verify(rows, spec, result)['check_status'], 'passed')
