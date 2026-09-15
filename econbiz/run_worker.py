"""Frozen package worker. All inputs verified before the only estimation route."""

import argparse
import hashlib
import json
import re
import traceback
from pathlib import Path

from .analysis_environment import check_environment
from .execution_spec import prepare_sample, compile_spec
from .state import WorkflowError


def load_json(path):
    def reject(value):
        raise WorkflowError(f'JSON 包含非有限值：{value}')
    return json.loads(Path(path).read_text('utf-8'), parse_constant=reject)


def save_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, allow_nan=False, indent=2)
        f.write('\n')


def main(package):
    parser = argparse.ArgumentParser(description='重跑已冻结分析包，不覆盖既有结果')
    parser.add_argument('--output', default='outputs')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.output):
        raise WorkflowError('输出目录只允许简单标识')
    package = Path(package).resolve()
    manifest = load_json(package / 'manifest.json')
    for relative, digest in manifest['files'].items():
        target = package / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts or target.is_symlink():
            raise WorkflowError('冻结文件路径无效')
        target.resolve().relative_to(package)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise WorkflowError(f'冻结输入或代码已改变：{relative}')
    expected = load_json(package / 'environment.json')
    actual = check_environment(expected)
    output = package / args.output
    output.mkdir(exist_ok=False)
    try:
        from .estimation import estimate
        from .numerical_check import verify_numerics
        spec = load_json(package / 'spec.json')
        if compile_spec(load_json(package / 'plan.json'), load_json(package / 'inventory.json')) != spec:
            raise WorkflowError('执行规则与冻结方案不一致')
        rows, audit = prepare_sample((package / 'input.csv').read_bytes(), spec)
        save_json(output / 'sample.json', audit)
        save_json(output / 'environment.json', actual)
        result = estimate(rows, spec['estimation'])
        save_json(output / 'result.json', result)
        verification = verify_numerics(rows, spec['estimation'], result)
        save_json(output / 'verification.json', verification)
        save_json(output / 'status.json', {'execution_status': 'completed',
                                         'check_status': verification['check_status']})
        print('计算完成；独立数值检查：' + verification['check_status'])
        return 0
    except Exception as exc:
        save_json(output / 'error.json', {'type': type(exc).__name__, 'message': str(exc)})
        traceback.print_exc()
        return 1
