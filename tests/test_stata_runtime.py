import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from econbiz.state import WorkflowError


class StataRuntimeTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.stata_runtime'), 'Stata runtime helper missing')
        from econbiz import stata_runtime
        return stata_runtime

    def test_missing_explicit_executable_never_falls_back(self):
        with self.assertRaises(WorkflowError):
            self.api().probe_stata('/nonexistent/econbiz-stata')

    def test_unsupported_platform_is_explicit(self):
        runtime = self.api()
        with patch.object(runtime.sys, 'platform', 'win32'), self.assertRaisesRegex(WorkflowError, 'macOS'):
            runtime.probe_stata('/nonexistent/econbiz-stata')

    def test_identity_change_rejected_before_execution(self):
        runtime = self.api()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'stata-mp'
            path.write_text('changed binary')
            with self.assertRaises(WorkflowError):
                runtime.check_stata_identity(dict(executable=str(path), executable_sha256='not the digest', ado_sha256={}))

    def test_inherited_environment_cannot_disable_stata_timeout(self):
        runtime = self.api()
        with tempfile.TemporaryDirectory() as root:
            script = Path(root) / 'analysis.do'
            script.write_text('exit, clear')
            with patch.dict(os.environ, {'ECONBIZ_WORKER_GROUP': '1'}), \
                    patch.object(runtime, 'check_stata_identity'), \
                    patch.object(runtime, 'run_process', return_value=subprocess.CompletedProcess([], 0, '', '')) as launch:
                runtime.run_stata({'executable': '/fake/stata'}, script, root, timeout=7)
            self.assertEqual(launch.call_args.kwargs['timeout'], 7)
            self.assertTrue(launch.call_args.kwargs['new_group'])

    def test_implementation_changes_affect_environment_identity(self):
        runtime = self.api()
        with tempfile.TemporaryDirectory() as root:
            binary = Path(root) / 'Stata.app/Contents/MacOS/stata'
            binary.parent.mkdir(parents=True)
            binary.write_text('binary')
            base = Path(root) / 'ado/base/m'
            base.mkdir(parents=True)
            for suffix in ('.mata', '.class', '.py', '.jar'):
                with self.subTest(suffix=suffix):
                    source = base / ('helper' + suffix)
                    source.write_text('original')
                    before = runtime._ado_identity(binary)
                    source.write_text('changed')
                    self.assertNotEqual(before, runtime._ado_identity(binary))

    @unittest.skipUnless(os.environ.get('ECONBIZ_TEST_STATA'), 'real Stata opt-in')
    def test_real_probe_reports_version_without_license_identity(self):
        env = self.api().probe_stata(os.environ['ECONBIZ_TEST_STATA'])
        self.assertEqual(env['version'], '19')
        self.assertIn(env['os'], {'MacOSX', 'Unix'})
        self.assertTrue(env['build_date'])
        self.assertEqual(len(env['executable_sha256']), 64)
        self.assertNotIn('serial', str(env).lower())
        self.api().check_stata_identity(env)
