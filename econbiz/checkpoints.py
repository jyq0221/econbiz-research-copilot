"""Content-checked manifests and additive restoration; never rewind history."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .files import describe_file, project_path, read_verified, verify_file, write_version
from .state import Project, WorkflowError, now, require_text
from .workspace import encode_json, require_id


def file_status(workspace, snapshot):
    statuses = []
    for key, artifact in snapshot['artifacts'].items():
        for version in [artifact] + snapshot['history'].get(key, []):
            refs = list(version.get('files', []))
            content = version['content']
            if version['kind'] == 'inventory':
                if 'input_ref' in content and content['input_ref'] not in refs:
                    refs.append(content['input_ref'])
                elif 'input_path' in content:
                    path = content['input_path']
                    try:
                        ref = describe_file(workspace.root, path, scope='external', role='legacy_inventory')
                        ref['sha256'] = content['input_sha256']
                        refs.append(ref)
                    except (WorkflowError, KeyError) as exc:
                        statuses.append(dict(artifact_id=key, version=version['version'], path=path,
                                             status='unavailable', included=False, error=str(exc)))
            for ref in refs:
                item = dict(artifact_id=key, version=version['version'], path=ref['path'],
                            reference=ref, included=ref['scope'] == 'project')
                try:
                    verify_file(workspace.root, ref)
                    item['status'] = 'available'
                except WorkflowError as exc:
                    item.update(status='unavailable', error=str(exc))
                statuses.append(item)
    return statuses


def create_checkpoint(workspace, label, reason):
    require_text(label, '检查点名称')
    require_text(reason, '检查点原因')
    snapshot = workspace.project.snapshot()
    statuses = file_status(workspace, snapshot)
    checkpoint_id = 'checkpoint-' + uuid4().hex
    relative = f'{workspace.layout["research_history"]}/checkpoints/{checkpoint_id}/checkpoint.json'
    checkpoint = dict(id=checkpoint_id, label=label, reason=reason, recorded_at=now(), path=relative,
                      snapshot=snapshot, file_status=statuses,
                      complete=all(s['status'] == 'available' and s['included'] for s in statuses))
    raw = encode_json(checkpoint)
    write_version(workspace.root, relative, raw)
    write_version(workspace.root, relative + '.sha256', hashlib.sha256(raw).hexdigest().encode('ascii'))
    return checkpoint


def _load(workspace, checkpoint_id):
    require_id(checkpoint_id)
    relative = f'{workspace.layout["research_history"]}/checkpoints/{checkpoint_id}/checkpoint.json'
    try:
        raw = project_path(workspace.root, relative).read_bytes()
        digest = project_path(workspace.root, relative + '.sha256').read_text('ascii')
        if hashlib.sha256(raw).hexdigest() != digest:
            raise WorkflowError('检查点内容校验失败')
        checkpoint = json.loads(raw)
        if checkpoint['id'] != checkpoint_id:
            raise WorkflowError('检查点标识不匹配')
        Project(checkpoint['snapshot'], base_dir=workspace.root)
        return checkpoint
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise WorkflowError(f'检查点不可读取：{checkpoint_id}：{exc}') from exc


def compare_checkpoints(workspace, left, right):
    a, b = _load(workspace, left), _load(workspace, right)
    aa, bb = a['snapshot']['artifacts'], b['snapshot']['artifacts']
    common = aa.keys() & bb.keys()
    return dict(added=sorted(bb.keys() - aa.keys()), removed=sorted(aa.keys() - bb.keys()),
                changed=sorted(k for k in common if aa[k] != bb[k]),
                dependency_changes=sorted(k for k in common if aa[k]['dependencies'] != bb[k]['dependencies']),
                file_status={'left': file_status(workspace, a['snapshot']), 'right': file_status(workspace, b['snapshot'])})


def restore_record(workspace, artifact_id, version, reason):
    require_text(reason, '恢复原因')
    old = workspace.project.version(artifact_id, version)
    for ref in old.get('files', []):
        read_verified(workspace.root, ref)
    if old['kind'] == 'inventory':
        content = old['content']
        if 'input_ref' in content:
            read_verified(workspace.root, content['input_ref'])
        elif 'input_path' in content:
            try:
                raw = Path(content['input_path']).read_bytes()
            except OSError as exc:
                raise WorkflowError('旧盘点来源缺失') from exc
            if hashlib.sha256(raw).hexdigest() != content['input_sha256']:
                raise WorkflowError('旧盘点来源改变')
    for dep, expected in old['dependencies'].items():
        current = workspace.project.require_usable(dep)
        if current['version'] != expected:
            raise WorkflowError(f'旧版依赖 {dep} v{expected} 与当前 v{current["version"]} 不符；需重选输入')
    if old['kind'] == 'plan':
        from .plans import validate_plan
        inventories = [workspace.project.artifact(k) for k in old['dependencies']
                       if workspace.project.artifact(k)['kind'] == 'inventory']
        if len(inventories) != 1:
            raise WorkflowError('恢复方案必须绑定一个有效盘点')
        validate_plan(old['content'], inventories[0]['content']['columns'])
    staged = workspace._stage(artifact_id, old['kind'], old['content'], list(old['dependencies']),
                              old.get('files', []), reason)
    if old['kind'] == 'plan':
        staged.mark(artifact_id, 'needs_decision', 'needs_decision', '恢复形成新方案版本，需重新确认')
    elif old['execution_status'] == 'completed' and old['check_status'] == 'passed':
        staged.mark(artifact_id, 'completed', 'passed', '旧内容及依赖可读；不提高证据等级')
    workspace._publish(staged)
    return workspace.project.artifact(artifact_id)
