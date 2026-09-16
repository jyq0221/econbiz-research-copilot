"""Bounded subprocesses: the owner reaps the entire POSIX process group."""

import os
import signal
import subprocess
from contextlib import ExitStack


def run_process(args, *, cwd, timeout, env=None, new_group=True, log_path=None):
    with ExitStack() as stack:
        log = stack.enter_context(open(log_path, 'x', encoding='utf-8')) if log_path else None
        return _run_process(args, cwd=cwd, timeout=timeout, env=env, new_group=new_group, log=log)


def _run_process(args, *, cwd, timeout, env, new_group, log):
    output = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                  encoding='utf-8', errors='replace') if log is None else dict(stdout=log, stderr=subprocess.STDOUT)
    process = subprocess.Popen(args, cwd=cwd, env=env,
                               start_new_session=new_group and os.name == 'posix', **output)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        # SIGKILL also stops descendants whose parent has already exited. A nested
        # worker shares its outer owner's group and leaves group cleanup to it.
        try:
            if new_group and os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    return subprocess.CompletedProcess(args, process.returncode, stdout or '', stderr or '')
