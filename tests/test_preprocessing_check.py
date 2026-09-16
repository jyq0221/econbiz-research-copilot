import csv
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from econbiz.preprocessing import prepare_data
from econbiz.state import WorkflowError


HAS_ANALYSIS = all(importlib.util.find_spec(name) for name in ('numpy', 'pandas'))
STATA_PATH = os.environ.get('ECONBIZ_TEST_STATA')
HAS_STATA = bool(STATA_PATH and Path(STATA_PATH).is_file())


def recipe(*steps):
    return {'schema_version': 1, 'keys': ['firm', 'year'], 'steps': list(steps)}


@unittest.skipUnless(HAS_ANALYSIS, 'analysis dependencies unavailable')
class PreparationCheckTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.preprocessing_check'), 'independent preparation checker missing')
        from econbiz.preprocessing_check import verify_preparation
        return verify_preparation

    def fixture(self):
        raw = b'firm,year,group,x,d\n001,2020,A,1,2\n001,2021,A,3,0\n001,2023,A,100,1\n002,2020,B,-1,4\n002,2021,B,1,2\n003,2020,A,,2\n'
        spec = recipe(
            dict(op='winsor', source='x', target='xw', lower=.25, upper=.75, by=['group']),
            dict(op='ln', source='xw', target='lx', invalid='missing'),
            dict(op='log1p', source='x', target='lp', invalid='missing'),
            dict(op='ratio', numerator='x', denominator='d', target='ratio', zero='missing'),
            dict(op='interaction', sources=['x', 'd'], target='xd'),
            dict(op='indicator', source='group', target='is_a', value='A', missing='missing'),
            dict(op='center', source='x', target='xc', by=['group']),
            dict(op='standardize', source='x', target='xz', by=['group'], ddof=1, zero='missing'),
            dict(op='lag', source='x', target='lag_x', entity=['firm'], time='year', interval=1),
            dict(op='difference', source='x', target='dx', entity=['firm'], time='year', interval=1),
            dict(op='filter', source='year', operator='ge', value=2020))
        return raw, spec

    def test_hand_computable_reference_and_all_operations(self):
        verify = self.api()
        raw = b'firm,year,x\n001,1,1\n002,1,3\n'
        spec = recipe(dict(op='winsor', source='x', target='xw', lower=.25, upper=.75, by=[]),
                      dict(op='center', source='xw', target='xc', by=[]))
        result = verify(raw, spec, b'firm,year,x,xw,xc\n001,1,1,1.5,-0.5\n002,1,3,2.5,0.5\n')
        self.assertEqual(result['check_status'], 'passed')
        self.assertEqual(result['reference']['engine'], 'independent_numpy_pandas')
        self.assertEqual(result['reference']['rtol'], 1e-9)
        self.assertEqual(result['reference']['atol'], 1e-12)
        raw, spec = self.fixture()
        actual, _ = prepare_data(raw, spec)
        with mock.patch('econbiz.preprocessing.prepare_data', side_effect=AssertionError('self replay forbidden')), \
                mock.patch('econbiz.preprocessing._quantile', side_effect=AssertionError('shared quantile forbidden')):
            self.assertEqual(verify(raw, spec, actual)['check_status'], 'passed')

    def test_mutated_numeric_missing_raw_key_order_and_headers_fail(self):
        verify = self.api()
        raw, spec = self.fixture()
        actual, _ = prepare_data(raw, spec)
        table = list(csv.reader(io.StringIO(actual.decode())))
        cases = []
        for name, value in [('xw', '999'), ('xw', ''), ('xw', 'NaN'), ('xw', 'inf'), ('firm', '999'), ('firm', ''), ('x', '1.0')]:
            mutated = [row[:] for row in table]
            mutated[1][table[0].index(name)] = value
            cases.append(mutated)
        cases.extend([table[:1] + table[2:3] + table[1:2] + table[3:], table[:-1], [table[0][::-1]] + table[1:]])
        for altered in cases:
            stream = io.StringIO(newline='')
            csv.writer(stream).writerows(altered)
            with self.subTest(altered=altered[:2]):
                self.assertEqual(verify(raw, spec, stream.getvalue().encode())['check_status'], 'failed')

    def test_no_steps_all_missing_empty_sample_and_constant_scale(self):
        verify = self.api()
        raw = b'firm,year,x,category\n001,1,,\n002,1,,A\n'
        specs = [recipe(), recipe(dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='missing')),
                 recipe(dict(op='indicator', source='category', target='a', value='A', missing='zero')),
                 recipe(dict(op='filter', source='year', operator='gt', value=2),
                        dict(op='winsor', source='x', target='w', lower=0, upper=1, by=[]))]
        for spec in specs:
            actual, _ = prepare_data(raw, spec)
            self.assertEqual(verify(raw, spec, actual)['check_status'], 'passed')

    def test_invalid_reference_input_is_not_treated_as_valid_missing(self):
        verify = self.api()
        spec = recipe(dict(op='ln', source='x', target='lx', invalid='missing'))
        for raw in [b'firm,year,x\n001,1,NA\n', b'firm,year,x\n001,1,1\n001,1,2\n']:
            with self.assertRaises(WorkflowError):
                verify(raw, spec, b'firm,year,x,lx\n001,1,NA,\n')

    def test_dependency_failure_is_explicit_and_extreme_scales_verify(self):
        verify = self.api()
        with mock.patch.dict('sys.modules', {'numpy': None}):
            with self.assertRaisesRegex(WorkflowError, '依赖'):
                verify(b'firm,year,x\n001,1,1\n', recipe(), b'firm,year,x\n001,1,1\n')
        spec = recipe(dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='missing'))
        for raw in [b'firm,year,x\n001,1,-1e200\n002,1,-1\n003,1,1\n004,1,1e200\n',
                    b'firm,year,x\n001,1,1e-200\n002,1,2e-200\n']:
            actual, _ = prepare_data(raw, spec)
            self.assertEqual(verify(raw, spec, actual)['check_status'], 'passed')

    def test_exact_large_integer_filter(self):
        verify = self.api()
        raw = b'firm,year,x\n001,1,9007199254740992\n'
        spec = recipe(dict(op='filter', source='x', operator='lt', value=9007199254740993))
        actual, _ = prepare_data(raw, spec)
        self.assertEqual(verify(raw, spec, actual)['check_status'], 'passed')

    def test_tiny_nonzero_pattern_is_not_erased_by_absolute_tolerance(self):
        verify = self.api()
        raw = b'firm,year,x,d\n001,1,1e-200,1\n'
        spec = recipe(dict(op='ratio', numerator='x', denominator='d', target='r', zero='error'))
        actual = b'firm,year,x,d,r\n001,1,1e-200,1,0\n'
        self.assertEqual(verify(raw, spec, actual)['check_status'], 'failed')

    def test_fixed_point_small_decimals_are_not_truncated_by_reference_parser(self):
        verify = self.api()
        spec = recipe(dict(op='ratio', numerator='x', denominator='d', target='r', zero='error'))
        raw = b'firm,year,x,d\n001,1,0.00000000000000001,1\n'
        correct, _ = prepare_data(raw, spec)
        for actual, wanted in [(correct, 'passed'),
                               (b'firm,year,x,d,r\n001,1,0.00000000000000001,1,0\n', 'failed')]:
            with self.subTest(wanted=wanted):
                self.assertEqual(verify(raw, spec, actual)['check_status'], wanted)
        raw = b'firm,year,x,d\n001,1,0.00000000000001953,1e-20\n'
        spec = recipe(dict(op='ratio', numerator='x', denominator='d', target='r', zero='error'),
                      dict(op='center', source='x', target='c', by=[]))
        actual, _ = prepare_data(raw, spec)
        self.assertEqual(verify(raw, spec, actual)['check_status'], 'passed')

    def test_centering_large_offsets_and_symmetric_decimals_preserves_variation(self):
        verify = self.api()
        spec = recipe(dict(op='center', source='x', target='c', by=[]),
                      dict(op='standardize', source='x', target='z', by=[], ddof=1, zero='error'))
        raw = b'firm,year,x\n001,1,10000000000000000\n002,1,10000000000000002\n003,1,10000000000000004\n'
        correct, _ = prepare_data(raw, spec)
        wrong = b'firm,year,x,c,z\n001,1,10000000000000000,0,0\n002,1,10000000000000002,2,0.76813653338739962\n003,1,10000000000000004,4,1.5362730667747992\n'
        for actual, wanted in [(correct, 'passed'), (wrong, 'failed')]:
            with self.subTest(wanted=wanted):
                self.assertEqual(verify(raw, spec, actual)['check_status'], wanted)
        for values in [('0.1', '0.2', '0.3'), ('-0.92', '-0.91', '-0.9'), ('-0.89', '-0.88', '-0.87'), ('-0.77', '-0.76', '-0.75')]:
            raw = ('firm,year,x\n' + ''.join(f'{i},1,{v}\n' for i, v in enumerate(values))).encode()
            actual, _ = prepare_data(raw, spec)
            with self.subTest(values=values):
                self.assertEqual(verify(raw, spec, actual)['check_status'], 'passed')

    @unittest.skipUnless(HAS_STATA, 'set ECONBIZ_TEST_STATA to opt into native Stata')
    def test_independent_reference_accepts_actual_native_all_operation_output(self):
        verify = self.api()
        from econbiz.preprocessing_script import render_preparation_script
        raw, spec = self.fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'input.csv').write_bytes(raw)
            (root / 'prepare.do').write_text(render_preparation_script(spec, backend='stata'))
            subprocess.run([STATA_PATH, '-b', '-q', 'do', 'prepare.do'], cwd=root, capture_output=True, timeout=40)
            self.assertTrue((root / 'processed.csv').exists(), (root / 'prepare.log').read_text()[-3000:])
            result = verify(raw, spec, (root / 'processed.csv').read_bytes())
            self.assertEqual(result['check_status'], 'passed', result['checks'])


if __name__ == '__main__':
    unittest.main()
