"""Read only checked, byte-bound linear model outputs; never run a new estimator."""

import hashlib
import json

from .files import read_verified
from .state import WorkflowError, json_copy


def load_checked_model(workspace, run_id):
    run = workspace.project.require_usable(run_id)
    data = run['content']
    if (run['kind'] != 'result' or data.get('execution_status') != 'completed'
            or data.get('check_status') != 'passed'):
        raise WorkflowError('比较需要实际完成并独立核验的正式运行')
    refs = {ref['path']: ref for ref in run['files'] if ref['scope'] == 'project'}

    def raw(name):
        path = data['package'] + '/' + name
        if path not in refs:
            raise WorkflowError('运行缺少登记证据：' + name)
        return read_verified(workspace.root, refs[path])

    try:
        pairs = [('plan', 'plan.json'), ('spec', 'spec.json'), ('result', 'outputs/result.json'),
                 ('sample', 'outputs/sample.json'), ('verification', 'outputs/parent-verification.json')]
        for key, name in pairs:
            if json.loads(raw(name)) != data[key]:
                raise WorkflowError('运行记录与冻结证据不一致：' + key)
        from .execution import validate_outputs
        from .execution_spec import prepare_sample
        from .numerical_check import verify_numerics
        result, sample, spec = data['result'], data['sample'], data['spec']
        if result['model'] != 'linear_fe':
            raise WorkflowError('首批比较只接收线性固定效应结果')
        validate_outputs(data, spec)
        if data['verification']['check_status'] != 'passed':
            raise WorkflowError('独立核验未通过')
        source = raw('input.csv')
        if hashlib.sha256(source).hexdigest() != data['input_sha256']:
            raise WorkflowError('输入标识不匹配')
        rows, expected = prepare_sample(source, spec)
        if expected != sample:
            raise WorkflowError('样本记录不匹配实际冻结输入')
        backend = data.get('backend', 'python')
        if verify_numerics(rows, spec['estimation'], result, backend=backend)['check_status'] != 'passed':
            raise WorkflowError('接收比较时独立数值复核未通过')
        if [p['term'] for p in result['parameters']] != result['actual_spec']['x']:
            raise WorkflowError('有效运行缺少参数或参数顺序不一致')
        plan = workspace.project.require_usable(data['plan_id'])
        if plan['version'] != data['plan_version'] or plan['content'] != data['plan']:
            raise WorkflowError('当前方案与运行不一致')
        variables = {}
        for field in result['actual_spec']['x'] + [result['actual_spec']['y']]:
            matching = [m for m in data['plan']['mapping'].values() if m['field'] == field]
            item = matching[0] if matching else {}
            variables[field] = dict(field=field, definition=item.get('definition'), unit=item.get('unit'),
                                    transform=item.get('transform'), source=item.get('source'))
        return json_copy(dict(run={'id': run_id, 'version': run['version']},
            plan={'id': data['plan_id'], 'version': data['plan_version']}, backend=backend,
            input_sha256=data['input_sha256'], parameters=result['parameters'], actual_spec=result['actual_spec'],
            sample_keys=sample['sample_keys'], sample=sample, controls=data['plan']['controls'], descriptive=result['descriptive'],
            diagnostics=result['diagnostics'], variables=variables, source_files=run['files']))
    except (KeyError, TypeError, ValueError, ImportError) as exc:
        raise WorkflowError('比较运行证据不完整或依赖不可用：' + str(exc)) from exc
