"""Versioned artifacts and decisions. Local, single-writer persistence only."""

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class WorkflowError(ValueError):
    """A workflow rule or persisted contract was violated."""


EXECUTION = {'pending', 'running', 'completed', 'failed', 'needs_decision', 'stale', 'not_applicable'}
CHECKS = {'pending', 'passed', 'failed', 'needs_decision', 'stale', 'not_applicable'}


def now():
    return datetime.now(timezone.utc).isoformat()


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f'{label} 必须是非空文本')


def json_copy(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError) as exc:
        raise WorkflowError('内容必须是可保存的 JSON，且不能包含 NaN 或无穷值') from exc


def write_json(path, content):
    """Atomic file replacement; the caller owns concurrency and directory policy."""
    encoded = json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    write_text(path, encoded)


def write_text(path, encoded):
    """Atomically replace a generated view or a serialized state file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
            temporary = f.name
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class Project:
    def __init__(self, state, *, base_dir=None):
        self.base_dir = Path(base_dir).resolve() if base_dir is not None else None
        self._state = json_copy(state)
        self._validate()

    @classmethod
    def create(cls, project_id, direction, *, base_dir=None):
        require_text(project_id, '项目标识')
        require_text(direction, '研究方向')
        return cls(dict(schema_version=1, project_id=project_id, direction=direction,
                        artifacts={}, history={}, decisions=[], events=[]), base_dir=base_dir)

    def clone(self):
        return Project(self.snapshot(), base_dir=self.base_dir)

    def version(self, artifact_id, version):
        current = self._get(artifact_id)
        if type(version) is not int or not 1 <= version <= current['version']:
            raise WorkflowError(f'版本不存在：{artifact_id} v{version}')
        return copy.deepcopy(current if version == current['version'] else self._state['history'][artifact_id][version - 1])

    def snapshot(self):
        return copy.deepcopy(self._state)

    def artifact(self, artifact_id):
        return copy.deepcopy(self._get(artifact_id))

    def _get(self, artifact_id):
        try:
            return self._state['artifacts'][artifact_id]
        except KeyError as exc:
            raise WorkflowError(f'产物不存在：{artifact_id}') from exc

    def _event(self, action, artifact_id, reason):
        self._state['events'].append(dict(action=action, artifact_id=artifact_id,
                                          reason=reason, at=now()))

    def _validate(self):
        try:
            s = self._state
            if s['schema_version'] != 1:
                raise WorkflowError('不支持此状态文件版本')
            require_text(s['project_id'], '项目标识')
            require_text(s['direction'], '研究方向')
            if not isinstance(s['artifacts'], dict) or not isinstance(s['history'], dict):
                raise WorkflowError('产物和历史必须是字典')
            if not isinstance(s['events'], list) or not isinstance(s['decisions'], list):
                raise WorkflowError('事件和决策必须是列表')
            for key, a in s['artifacts'].items():
                for record in [a] + s['history'].get(key, []):
                    self._validate_files(record.get('files', []))
                    if 'input_ref' in record.get('content', {}):
                        self._validate_files([record['content']['input_ref']])
                require_text(a['kind'], '产物种类')
                if a['id'] != key or type(a['version']) is not int or a['version'] < 1:
                    raise WorkflowError('产物标识或版本无效')
                if a['execution_status'] not in EXECUTION or a['check_status'] not in CHECKS:
                    raise WorkflowError('未知执行或检查状态')
                if not isinstance(a['content'], dict) or not isinstance(a['dependencies'], dict):
                    raise WorkflowError('内容和依赖必须是字典')
                for dep, version in a['dependencies'].items():
                    if dep not in s['artifacts'] or type(version) is not int or not 1 <= version <= s['artifacts'][dep]['version']:
                        raise WorkflowError('依赖引用或版本无效')
                old = s['history'][key]
                if [v['version'] for v in old] != list(range(1, a['version'])):
                    raise WorkflowError('历史版本不连续')
                for previous in old:
                    if previous['id'] != key or previous['kind'] != a['kind']:
                        raise WorkflowError('历史产物标识或种类无效')
                    if previous['execution_status'] not in EXECUTION or previous['check_status'] not in CHECKS:
                        raise WorkflowError('历史状态无效')
                    require_text(previous['created_at'], '历史创建时间')
                    if not isinstance(previous['content'], dict) or not isinstance(previous['dependencies'], dict):
                        raise WorkflowError('历史内容或依赖损坏')
                    for dep, version in previous['dependencies'].items():
                        if dep not in s['artifacts'] or type(version) is not int or not 1 <= version <= s['artifacts'][dep]['version']:
                            raise WorkflowError('历史依赖引用损坏')
            visited = set()
            def visit(key, ancestors):
                if key in ancestors:
                    raise WorkflowError('依赖关系存在循环')
                if key not in visited:
                    for dep in s['artifacts'][key]['dependencies']:
                        visit(dep, ancestors | {key})
                    visited.add(key)
            for key in s['artifacts']:
                visit(key, set())
            for d in s['decisions']:
                require_text(d['actor'], '确认者')
                require_text(d['reason'], '确认理由')
                require_text(d['evidence'], '确认证据位置')
                a = s['artifacts'][d['artifact_id']]
                if a['kind'] != 'plan' or not 1 <= d['version'] <= a['version']:
                    raise WorkflowError('确认引用无效')
        except (KeyError, TypeError, AttributeError) as exc:
            raise WorkflowError('状态文件结构损坏') from exc

    @staticmethod
    def _validate_files(files):
        from .files import validate_reference
        if not isinstance(files, list):
            raise WorkflowError('文件引用必须是列表')
        for ref in files:
            validate_reference(ref)

    def _prepare_dependencies(self, artifact_id, dependencies, *, script_source=False):
        if not isinstance(dependencies, (list, tuple, dict)):
            raise WorkflowError('依赖必须是标识列表')
        deps = {}
        def reaches(key):
            return key == artifact_id or any(reaches(child) for child in self._get(key)['dependencies'])
        for dep in dependencies:
            require_text(dep, '依赖标识')
            if dep in deps or reaches(dep):
                raise WorkflowError('依赖重复、自引用或存在循环')
            if script_source and self._get(dep)['kind'] == 'script_run':
                self.require_executed_script(dep)
            else:
                self.require_usable(dep)
            deps[dep] = self._get(dep)['version']
        return deps

    def add(self, artifact_id, kind, content, dependencies=(), *, files=()):
        require_text(artifact_id, '产物标识')
        require_text(kind, '产物种类')
        if artifact_id in self._state['artifacts']:
            raise WorkflowError(f'产物已存在：{artifact_id}；请显式修订')
        content = json_copy(content)
        if not isinstance(content, dict):
            raise WorkflowError('产物内容必须是字典')
        files = json_copy(list(files))
        self._validate_files(files)
        deps = self._prepare_dependencies(artifact_id, dependencies,
                                          script_source=kind == 'source' and 'script_run' in content)
        if kind == 'plan':
            from .research_history import prepare_plan_content
            content = prepare_plan_content(self, content)
            self._validate_plan_inputs(content, deps)
        self._state['artifacts'][artifact_id] = dict(
            id=artifact_id, kind=kind, version=1, content=content, dependencies=deps, files=files,
            execution_status='pending', check_status='pending', created_at=now())
        self._state['history'][artifact_id] = []
        self._event('added', artifact_id, '登记新产物')

    def _validate_plan_inputs(self, content, dependencies):
        from .plans import validate_plan
        inventories = [self._get(key) for key in dependencies if self._get(key)['kind'] == 'inventory']
        if len(inventories) != 1:
            raise WorkflowError('正式方案必须绑定一个数据盘点版本')
        validate_plan(content, inventories[0]['content']['columns'])

    def _check_dependencies(self, artifact_id):
        artifact = self._get(artifact_id)
        for dep, version in artifact['dependencies'].items():
            if self._get(dep)['version'] != version:
                raise WorkflowError(f'{artifact_id} 依赖的 {dep} 版本已变更')
            if (artifact['kind'] == 'source' and artifact['content'].get('script_run') == dict(id=dep, version=version)
                    and self._get(dep)['kind'] == 'script_run'):
                self.require_executed_script(dep)
            else:
                self.require_usable(dep)

    def require_executed_script(self, artifact_id):
        """Only execution provenance; callers must not treat this as statistics."""
        from .files import verify_file
        artifact = self._get(artifact_id)
        if (artifact['kind'] != 'script_run' or artifact['execution_status'] != 'completed'
                or artifact['check_status'] != 'pending' or not artifact['content'].get('finished_at')):
            raise WorkflowError('项目脚本执行证据不完整或已失效')
        for ref in artifact.get('files', []):
            verify_file(self.base_dir, ref)
        self._check_dependencies(artifact_id)
        return self.artifact(artifact_id)

    def require_usable(self, artifact_id):
        if not hasattr(self, '_checking'):
            self._checking = set()
        if artifact_id in self._checking:
            raise WorkflowError(f'产物消费引用存在循环：{artifact_id}')
        self._checking.add(artifact_id)
        try:
            return self._require_usable(artifact_id)
        finally:
            self._checking.remove(artifact_id)

    def _require_usable(self, artifact_id):
        from .files import verify_file
        a = self._get(artifact_id)
        if a['execution_status'] != 'completed' or a['check_status'] != 'passed':
            raise WorkflowError(f'{artifact_id} 尚未完成并通过检查，不能继续消费')
        for ref in a.get('files', []):
            verify_file(self.base_dir, ref)
        if a['kind'] == 'inventory' and {'input_ref', 'input_path'} & a['content'].keys():
            self.read_inventory_bytes(artifact_id)
        self._check_dependencies(artifact_id)
        if a['kind'] in {'research_task', 'session_note'}:
            from .records import reference
            for output in a['content'].get('outputs', []):
                reference(self, output)
        if a['kind'] == 'user_decision':
            from .records import reference
            reference(self, {'artifact_id': a['content']['plan_id'], 'version': a['content']['plan_version']}, usable=False)
        return self.artifact(artifact_id)

    def read_inventory_bytes(self, artifact_id):
        from .files import read_verified
        artifact = self._get(artifact_id)
        if artifact['kind'] != 'inventory':
            raise WorkflowError('所选产物不是数据盘点')
        report = artifact['content']
        if 'input_ref' in report:
            raw = read_verified(self.base_dir, report['input_ref'])
        else:
            try:
                path = Path(report['input_path'])
                if not path.is_absolute():
                    raise WorkflowError('旧盘点来源需要绝对路径')
                raw = path.read_bytes()
            except (OSError, KeyError, TypeError) as exc:
                raise WorkflowError(f'{artifact_id} 的原始输入不可读取，需重新核实') from exc
        if 'input_sha256' in report and hashlib.sha256(raw).hexdigest() != report['input_sha256']:
            raise WorkflowError(f'{artifact_id} 的原始输入已改变，需重新盘点并修订下游')
        return raw

    def _invalidate(self, artifact_id, reason):
        queue = [artifact_id]
        seen = {artifact_id}
        while queue:
            parent = queue.pop()
            for key, a in self._state['artifacts'].items():
                if parent in a['dependencies'] and key not in seen:
                    a.update(execution_status='stale', check_status='stale')
                    self._event('invalidated', key, reason)
                    seen.add(key)
                    queue.append(key)

    def revise(self, artifact_id, content, reason, *, dependencies=None, files=None):
        require_text(reason, '修订原因')
        a = self._get(artifact_id)
        content = json_copy(content)
        if not isinstance(content, dict):
            raise WorkflowError('内容必须是字典')
        refs = json_copy(a.get('files', []) if files is None else list(files))
        self._validate_files(refs)
        deps = self._prepare_dependencies(artifact_id, a['dependencies'] if dependencies is None else dependencies,
                                          script_source=a['kind'] == 'source' and 'script_run' in content)
        if a['kind'] == 'plan':
            from .research_history import prepare_plan_content
            if content != a['content'] or deps != a['dependencies']:
                content = prepare_plan_content(self, content)
            self._validate_plan_inputs(content, deps)
        self._state['history'][artifact_id].append(copy.deepcopy(a))
        a.update(version=a['version'] + 1, content=content, dependencies=deps, files=refs,
                 execution_status='pending', check_status='pending')
        self._event('revised', artifact_id, reason)
        self._invalidate(artifact_id, reason)

    def mark(self, artifact_id, execution_status, check_status, reason):
        require_text(reason, '状态依据')
        if execution_status not in EXECUTION or check_status not in CHECKS:
            raise WorkflowError('未知执行或检查状态')
        a = self._get(artifact_id)
        if a['execution_status'] == 'stale' or a['check_status'] == 'stale':
            raise WorkflowError('过期产物必须显式修订并重新检查，不能通过切换状态恢复')
        if execution_status in {'running', 'completed'}:
            self._check_dependencies(artifact_id)
        if a['kind'] == 'result' and (execution_status == 'completed' or a['execution_status'] == 'completed'):
            a['has_completed_result'] = True
        a.update(execution_status=execution_status, check_status=check_status)
        self._event('status_changed', artifact_id, reason)
        if execution_status != 'completed' or check_status != 'passed':
            self._invalidate(artifact_id, reason)

    def finish_result(self, artifact_id, content, files, execution_status, check_status, reason):
        return self._finish_attempt(artifact_id, content, files, execution_status, check_status,
                                    reason, kind='result')

    def finish_script_run(self, artifact_id, content, files, execution_status, reason):
        """Execution evidence never certifies a custom script's statistics."""
        return self._finish_attempt(artifact_id, content, files, execution_status,
                                    'pending' if execution_status == 'completed' else 'failed',
                                    reason, kind='script_run')

    def _finish_attempt(self, artifact_id, content, files, execution_status, check_status, reason, *, kind):
        """Finalize a running attempt, retaining frozen dependencies even on failure.

        Unlike a research revision, finalizing failure evidence cannot require its
        upstream source to remain usable. A changed upstream always forces failure.
        """
        require_text(reason, '收尾依据')
        a = self._get(artifact_id)
        if (a['kind'] != kind or a['execution_status'] not in {'running', 'stale'}
                or a['content'].get('finished_at')):
            raise WorkflowError('仅可收尾未结束的正式运行；重跑须用新标识')
        allowed_checks = {'pending', 'failed'} if kind == 'script_run' else {'passed', 'failed'}
        if execution_status not in {'completed', 'failed'} or check_status not in allowed_checks:
            raise WorkflowError('运行收尾必须明确完成/失败及检查结果')
        if execution_status == 'failed' and check_status == 'passed':
            raise WorkflowError('失败运行不能标为核验通过')
        content, refs = json_copy(content), json_copy(list(files))
        if not isinstance(content, dict):
            raise WorkflowError('运行内容必须是字典')
        self._validate_files(refs)
        try:
            if a['execution_status'] == 'stale':
                raise WorkflowError('运行期间上游修订导致本次冻结依赖过期')
            self._check_dependencies(artifact_id)
        except WorkflowError as exc:
            content['dependency_error'] = str(exc)
            content['error'] = (content.get('error') or '') + '\n运行期间上游变化：' + str(exc)
            execution_status, check_status = 'failed', 'failed'
        content.update(execution_status=execution_status, check_status=check_status)
        self._state['history'][artifact_id].append(copy.deepcopy(a))
        a.update(version=a['version'] + 1, content=content, files=refs,
                 execution_status=execution_status, check_status=check_status,
                 has_completed_result=bool(content.get('result')))
        self._event(kind + '_finalized', artifact_id, reason)
        self._invalidate(artifact_id, '运行已收尾，请消费明确的最终版本')
        return self.artifact(artifact_id)

    def approve(self, artifact_id, actor, reason, evidence):
        """Record a caller-supplied human decision; this is not authentication."""
        for value, label in [(actor, '确认者'), (reason, '确认理由'), (evidence, '确认证据位置')]:
            require_text(value, label)
        a = self._get(artifact_id)
        if a['kind'] != 'plan' or a['execution_status'] in {'stale', 'failed', 'running'}:
            raise WorkflowError('此产物不能作为当前方案确认')
        self._check_dependencies(artifact_id)
        from .plans import validate_plan
        inventory = [self._get(dep) for dep in a['dependencies'] if self._get(dep)['kind'] == 'inventory']
        if len(inventory) != 1:
            raise WorkflowError('方案必须绑定一个数据盘点版本')
        validate_plan(a['content'], inventory[0]['content']['columns'],
                      require_supported=a['content'].get('execution_route') != 'project_script')
        if a['check_status'] in {'failed', 'stale'}:
            raise WorkflowError('检查失败的方案不能确认')
        evidence_path = Path(evidence)
        if '..' in evidence_path.parts:
            raise WorkflowError('确认证据路径不能包含上级跳转')
        if evidence_path.is_absolute() and self.base_dir is not None:
            try:
                evidence_path = evidence_path.relative_to(self.base_dir)
            except ValueError:
                pass
        for key, record in self._state['artifacts'].items():
            if record['kind'] != 'user_decision':
                continue
            for version in [record] + self._state['history'][key]:
                if any(ref['path'] == evidence_path.as_posix() for ref in version.get('files', [])):
                    if version['version'] != record['version']:
                        raise WorkflowError('确认摘录已修订，不能使用旧版摘录')
                    self.require_usable(key)
                    if version['content']['plan_id'] != artifact_id or version['content']['plan_version'] != a['version']:
                        raise WorkflowError('确认摘录与当前方案版本不符')
        self._state['decisions'].append(dict(artifact_id=artifact_id, version=a['version'],
                                             actor=actor, reason=reason, evidence=evidence, at=now()))
        a.update(execution_status='completed', check_status='passed')
        self._event('approved', artifact_id, reason)

    def save(self, path):
        self._validate()
        write_json(path, self._state)

    @classmethod
    def load(cls, path):
        try:
            project = cls(json.loads(Path(path).read_text(encoding='utf-8')), base_dir=Path(path).parent)
        except (OSError, ValueError, TypeError) as exc:
            raise WorkflowError(f'不能加载研究状态：{exc}') from exc
        for key in list(project._state['artifacts']):
            if project._get(key)['execution_status'] == 'running':
                project._get(key).update(execution_status='failed', check_status='pending')
                if project._get(key)['kind'] == 'script_run':
                    a = project._get(key)
                    a['check_status'] = 'failed'
                    a['content'].update(finished_at=now(), execution_status='failed', check_status='failed',
                        error='上次宿主中断，保留运行目录及部分文件；须使用新标识重跑',
                        result_output_present=not a['content'].get('preparation_only', False))
                project._event('interrupted', key, '上次执行中断；保留证据，需显式重跑')
                project._invalidate(key, '上游执行中断')
        return project
