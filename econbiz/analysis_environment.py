"""Versioned optional analysis runtime; importing the core stays dependency free."""

import importlib.metadata
import platform
import sys

from .state import WorkflowError

PINS = {'numpy': '2.0.2', 'scipy': '1.13.1', 'pandas': '2.3.3',
        'linearmodels': '6.1', 'openpyxl': '3.1.5', 'statsmodels': '0.14.6'}
SUPPORTING = ('formulaic', 'pyhdfe', 'setuptools-scm', 'packaging', 'mypy-extensions',
              'interface-meta', 'wrapt', 'python-dateutil', 'pytz', 'tzdata', 'six',
              'patsy', 'et-xmlfile', 'typing-extensions')


def environment():
    versions = {}
    for name, expected in PINS.items():
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise WorkflowError('缺少分析依赖；请在研究环境安装：python3 -m pip install ".[analysis]"') from exc
        if versions[name] != expected:
            raise WorkflowError(f'{name}={versions[name]} 尚未验收；已验证版本是 {expected}。请使用固定分析依赖')
    for name in SUPPORTING:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return dict(python=platform.python_version(), executable=sys.executable,
                platform=platform.platform(), packages=versions)


def check_environment(expected):
    actual = environment()
    if actual['python'] != expected['python'] or actual['packages'] != expected['packages']:
        raise WorkflowError('运行环境与冻结环境版本不一致；须在明确的新环境下重新登记并核验')
    return actual
