import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class ProcessTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('econbiz.processes'), 'process lifecycle helper missing')
        from econbiz.processes import run_process
        return run_process

    def test_normal_completion_returns_captured_output(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.api()([sys.executable, '-c', 'print("finished")'], cwd=root, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'finished')

    @unittest.skipUnless(os.name == 'posix', 'POSIX process groups')
    def test_timeout_kills_descendant_before_it_can_write(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'orphan.txt'
            child = 'import time; from pathlib import Path; time.sleep(.8); Path("orphan.txt").write_text("bad")'
            parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); print("started",flush=True); time.sleep(10)'
            with self.assertRaises(subprocess.TimeoutExpired):
                self.api()([sys.executable, '-c', parent], cwd=root, timeout=.2)
            time.sleep(.9)
            self.assertFalse(target.exists(), 'descendant survived the worker timeout')

    @unittest.skipUnless(os.name == 'posix', 'POSIX process groups')
    def test_cancellation_reaps_the_launched_process(self):
        run = self.api()
        original = subprocess.Popen.communicate
        processes = []
        def interrupted(process, *args, **kwargs):
            if not processes:
                processes.append(process)
                raise KeyboardInterrupt()
            return original(process, *args, **kwargs)
        with tempfile.TemporaryDirectory() as root, patch.object(subprocess.Popen, 'communicate', interrupted):
            with self.assertRaises(KeyboardInterrupt):
                run([sys.executable, '-c', 'import time; time.sleep(10)'], cwd=root, timeout=5)
        self.assertIsNotNone(processes[0].returncode)
