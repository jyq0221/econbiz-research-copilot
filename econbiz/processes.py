"""Bounded subprocesses: the owner reaps the entire POSIX process group."""

import os
import signal
import subprocess


def run_process(args, *, cwd, timeout, env=None, new_group=True):
    process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8',
                               errors='replace', start_new_session=new_group and os.name == 'posix')
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
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
