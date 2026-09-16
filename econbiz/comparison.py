"""Versioned model comparisons with explicit identities and actual sample differences."""

import itertools
import json

from .comparison_input import load_checked_model
from .files import read_verified
from .state import WorkflowError, now, require_text, json_copy
from .workspace import encode_json, require_id


def compare_sample_keys(left, right):
    def keys(rows):
        if not isinstance(rows, list) or any(not isinstance(k, list) or len(k) != 2 or
                any(not isinstance(v, str) or not v for v in k) for k in rows):
            raise WorkflowError('样本键须为两个非空文本字段')
        result = set(map(tuple, rows))
        if len(result) != len(rows):
            raise WorkflowError('样本键重复')
        return result
    a, b = keys(left), keys(right)
    return dict(same_sample=a == b, intersection_count=len(a & b),
                left_only=[list(k) for k in sorted(a-b)], right_only=[list(k) for k in sorted(b-a)])


def _variables(workspace, variables, models):
    if not isinstance(variables, list) or not variables:
        raise WorkflowError('须提供明确的变量身份映射')
    by_run = {m['run']['id']: m for m in models}
    seen, assigned, deps = set(), set(), []
    expected = {(r, f) for r, m in by_run.items() for f in m['variables']}
    for v in variables:
        if not isinstance(v, dict) or set(v) != {'id','label','definition','unit','transform','members','evidence_refs'}:
            raise WorkflowError('变量映射字段不完整')
        require_id(v['id'])
        require_text(v['label'], '变量标签')
        if v['id'] in seen:
            raise WorkflowError('变量身份重复')
        seen.add(v['id'])
        for key in ('definition','unit','transform'):
            if v[key] is not None:
                require_text(v[key], key)
        members = v['members']
        if not isinstance(members, dict) or not members:
            raise WorkflowError('变量成员须明确对应运行与字段')
        if len(members) > 1 and any(v[k] is None for k in ('definition','unit','transform')):
            raise WorkflowError('未知变量定义不可自动跨列对齐；请分别登记身份')
        roles = set()
        for r, f in members.items():
            if not isinstance(f, str) or (r, f) not in expected or (r, f) in assigned:
                raise WorkflowError('变量映射不存在或同一字段重复映射')
            assigned.add((r, f))
            m = by_run[r]
            roles.add('y' if f == m['actual_spec']['y'] else 'x')
            for key in ('definition','unit','transform'):
                original = m['variables'][f][key]
                if original is not None and v[key] is not None and original != v[key]:
                    raise WorkflowError('变量映射与实际方案定义冲突：' + f + '.' + key)
        if len(roles) > 1:
            raise WorkflowError('因变量与解释变量须分别登记身份')
        if not isinstance(v['evidence_refs'], list):
            raise WorkflowError('变量来源须为版本引用列表')
        for ref in v['evidence_refs']:
            if not isinstance(ref, dict) or set(ref) != {'artifact_id','version'}:
                raise WorkflowError('变量来源引用不完整')
            source = workspace.project.require_usable(ref['artifact_id'])
            if type(ref['version']) is not int or source['version'] != ref['version']:
                raise WorkflowError('变量来源版本已变更')
            deps.append(ref['artifact_id'])
    if assigned != expected:
        raise WorkflowError('变量映射必须覆盖因变量及全部回归变量')
    return list(dict.fromkeys(deps))


def _explain(keys, other):
    unexplained = set(map(tuple, keys))
    evidence = []
    for step in other['sample']['steps']:
        matched = unexplained & set(map(tuple, step['dropped_keys']))
        if matched:
            evidence.append(dict(rule=step['rule'], keys=[list(k) for k in sorted(matched)],
                                 source_run=other['run']))
            unexplained -= matched
    return dict(evidence=evidence, unresolved_keys=[list(k) for k in sorted(unexplained)])


def _content(workspace, *, columns, variables, title, display_terms, stars, created_at):
    require_text(title, '比较标题')
    if not isinstance(columns, list) or len(columns) < 2:
        raise WorkflowError('比较至少需要两个明确运行')
    models, seen = [], set()
    for col in columns:
        if not isinstance(col, dict) or set(col) != {'run_id','title','role'}:
            raise WorkflowError('每列须明确 run_id/title/role')
        require_id(col['run_id'])
        require_text(col['title'], '模型标题')
        if col['role'] not in {'baseline','robustness','other'} or col['run_id'] in seen:
            raise WorkflowError('模型角色非法或运行重复')
        seen.add(col['run_id'])
        models.append(dict(load_checked_model(workspace, col['run_id']), title=col['title'], role=col['role']))
    deps = _variables(workspace, variables, models)
    from .comparison_display import significance_marks
    significance_marks(.5, stars)
    terms = [v['id'] for v in variables if any(f != m['actual_spec']['y']
             for r, f in v['members'].items() for m in models if m['run']['id'] == r)]
    if display_terms is not None and (not isinstance(display_terms, list) or not display_terms or
            len(set(display_terms)) != len(display_terms) or any(t not in terms for t in display_terms)):
        raise WorkflowError('展示变量须为不重复的解释变量身份列表')
    differences = []
    for a, b in itertools.combinations(models, 2):
        diff = compare_sample_keys(a['sample_keys'], b['sample_keys'])
        changes = [k for k in ('y','x','fixed_effects','standard_errors','entity','time')
                   if a['actual_spec'][k] != b['actual_spec'][k]]
        differences.append(dict(diff, left=a['run']['id'], right=b['run']['id'],
            changed_settings=changes, input_changed=a['input_sha256'] != b['input_sha256'],
            key_semantics='按实际文本键比较；跨数据版本的代码体系和观察单位仍须研究者核实',
            left_only_reasons=_explain(diff['left_only'], b), right_only_reasons=_explain(diff['right_only'], a)))
    return dict(schema_version=1, title=title, created_at=created_at, columns=columns, variables=variables,
                display_terms=display_terms, stars=list(stars), models=models, differences=differences), deps


def write_model_comparison(workspace, comparison_id, *, columns, variables, title,
                           display_terms=None, stars=(), reason):
    require_id(comparison_id)
    # Normalize to JSON lists so in-memory and reopened records are identical.
    args = json_copy(dict(columns=columns, variables=variables, title=title,
                          display_terms=display_terms, stars=stars, created_at=now()))
    content, metadata_deps = _content(workspace, **args)
    from .comparison_display import build_display, render_comparison_markdown
    version = workspace._version_number(comparison_id)
    prefix = f'{workspace.layout["research_reports"]}/{comparison_id}/v{version:04d}'
    writes = [(prefix+'/comparison.json', encode_json(content)),
              (prefix+'/comparison.md', render_comparison_markdown(build_display(content)).encode('utf-8'))]
    files = [workspace._file(p, b, 'model_comparison') for p, b in writes]
    deps = list(dict.fromkeys([c['run_id'] for c in columns] + metadata_deps))
    staged = workspace._stage(comparison_id, 'model_comparison', content, deps, files, reason)
    staged.mark(comparison_id, 'completed', 'passed', '来源、样本与比较契约通过；不认证因果解释')
    workspace._publish(staged, writes)
    return workspace.project.artifact(comparison_id)


def read_model_comparison(workspace, comparison_id):
    a = workspace.project.require_usable(comparison_id)
    if a['kind'] != 'model_comparison':
        raise WorkflowError('需要模型比较记录')
    try:
        refs = [r for r in a['files'] if r['path'].endswith('/comparison.json')]
        if len(refs) != 1 or json.loads(read_verified(workspace.root, refs[0])) != a['content']:
            raise WorkflowError('比较内容与登记字节不一致')
        c = a['content']
        rebuilt, _ = _content(workspace, **{k:c[k] for k in
            ('columns','variables','title','display_terms','stars','created_at')})
        if rebuilt != c:
            raise WorkflowError('比较来源或派生内容不一致')
        return a
    except (ValueError, KeyError, TypeError) as exc:
        raise WorkflowError('比较记录损坏：' + str(exc)) from exc
