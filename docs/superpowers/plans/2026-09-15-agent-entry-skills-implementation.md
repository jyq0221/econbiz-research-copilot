# Agent 入口与 Skills：阶段 A 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让最终用户 clone 后在宿主 Agent 中开始研究准备，自动使用合适的 Skill，并在自己的项目中保存、核实和接续材料、科研讨论、任务及文件版本。

**Architecture:** 保留现有 `Project` 状态及依赖系统，增加文件引用、工作区服务和研究记录契约；宿主 Agent 负责研究推理，Skills 指导调用同一组 Python 接口。以 `.agents/skills/` 为维护源，同步普通文件到 `.claude/skills/`，共用研究手册和工具约定。

**Tech Stack:** Python 3.9+ 标准库、unittest、Markdown、JSON、项目级 Skills；Git 用于维护代码，用户研究 Git 为可选能力。

---

日期：2026-09-15。状态：计划已整理，任务均未执行。

设计依据：[入口与 Skills 设计方案 v0.3](../specs/2026-09-15-agent-entry-skills-design.md)。本地基线：[实施前检查](../../implementation-readiness.md)。

用户本轮明确选择“检查并整理实施计划”。本文件不表示已创建入口或实现新功能。开始实施时沿已有任务顺序执行，不默认启动子代理或新任务；工作方式如需调整，遵循用户当时的选择。

## 一、交付范围和顺序

当前工作目录只维护 GitHub 产品。所有自动化测试在临时目录建立模拟项目，运行用户研究流程不得污染维护根目录。

| 批次 | 对应任务 | 可交付结果 | 批次完成条件 |
| --- | --- | --- | --- |
| A0：开发基线 | 0 | 现有完整内容有可恢复的本地提交 | 56 项原有测试保留通过，明确本轮文件范围 |
| A1：材料与文件版本 | 1—3 | 三类目录、实际文件版本、路径校验、检查点、恢复 | 旧项目可读；移动、损坏、中断、历史恢复测试通过 |
| A2：科研记录与任务 | 4—6 | 讨论/文献/决定、持续任务、方案依赖和接续概览 | 来源、更正、探索历史和授权绑定可核对 |
| A3：入口与方法 | 7—8 | 五个 Skills、共享模板、双宿主分发 | 入口可区分维护/研究，包内容和链接通过检查 |
| A4：用户试用 | 9—10 | 可选研究 Git、真实宿主验收、学生说明 | 记录实际平台与行为证据；缺项明确列出 |

A1—A4 使用同一套状态与文件约定。阶段 A 不增加正式回归执行或宣称结果已复现；描述统计、固定效应估计、生成脚本的正式运行与独立数值核对属于阶段 B。第九部分列出后续交接及其验收范围。

Git 可选功能不阻塞不使用 Git 的研究准备试用；某宿主未完成实测时，只能说明该平台的适配文件已准备，不能宣称兼容已经验证。

## 二、文件职责

下列路径相对于维护仓库根目录，除标注修改外均为拟建。

| 文件 | 职责 |
| --- | --- |
| `econbiz/state.py`（修改） | 保持状态权威性；增加运行时项目根、版本读取、文件引用检查、显式依赖修订和副本接口 |
| `econbiz/files.py` | 解析来源路径、流式校验、写入不可静默覆盖的版本文件 |
| `econbiz/workspace.py` | 建项、打开、布局映射、材料导入和记录保存；统一保存顺序 |
| `econbiz/checkpoints.py` | 检查点清单、差异、旧版恢复；不回滚整个状态历史 |
| `econbiz/records.py` | 文献、概念草案、研究讨论、更正、确认摘录和任务的结构契约 |
| `econbiz/progress.py` | 根据当前状态和材料生成进度视图、会话摘要与恢复摘要 |
| `econbiz/research_history.py` | 统一检查是否已有结果暴露及其探索记录要求 |
| `econbiz/plans.py`（修改） | 方案登记/修订共用契约，增加文献和讨论依赖 |
| `econbiz/candidates.py`（修改） | 教学规则保留，复用文件读取、Project 副本和历史检查 |
| `econbiz/cli.py`（修改） | 对接新的建项/保存路径；保留现有命令和旧项目兼容 |
| `econbiz/research_git.py` | 可选研究 Git 的范围检查、选择性提交与结果报告 |
| `AGENTS.md`、`CLAUDE.md` | 维护/研究任务识别，统一研究入口与宿主适配 |
| `.agents/skills/econbiz-*/SKILL.md` | 五个 Skills 的发现描述、工作流程、边界和资源入口 |
| `.agents/skills/econbiz-*/assets/` | 六类研究模板及所需教学资源 |
| `.claude/skills/econbiz-*/` | 维护者生成、内容一致、随 Git 发布的普通文件副本 |
| `docs/research-handbook/principles.md` | 通用研究原则、指导风格和能力边界 |
| `docs/research-handbook/tool-contracts.md` | Agent 可直接采用的 Python 调用示例、输入输出和失败处理 |
| `docs/research-handbook/project-records.md` | 目录、记录类型、来源含义、版本和恢复规则 |
| `docs/research-handbook/teaching-cases.md` | 设计第 5.4 节三个教学情境与实际验证方式 |
| `scripts/sync_skills.py` | 同步两种宿主副本及只读检查模式 |
| `tests/test_files.py`、`tests/test_workspace.py` | 文件、路径、布局、导入和中断验证 |
| `tests/test_checkpoints.py`、`tests/test_records.py`、`tests/test_progress.py` | 历史、研究记录、任务与恢复验证 |
| `tests/test_research_history.py`、`tests/test_skills_package.py`、`tests/test_research_git.py` | 探索规则、打包和可选 Git 验证 |
| `tests/agent_cases/README.md`、`tests/agent_cases/cases.json` | 真实 Agent 行为验收方法与输入案例 |
| `docs/agent-entry-validation.md` | 自动化结果、宿主实测记录和未完成条件 |
| `README.md`、`docs/development-guide.md`、`docs/design-and-development-standard.md`（修改） | 学生入口、开发方法和版本一致的研究标准 |

保持当前 `schema_version=1` 的旧项目可读性：新字段在旧记录中可缺省，但已存在的新字段必须验证。若实施中发现必须进行破坏性结构变化，先编写明确迁移器及旧文件测试，再升级 schema；不直接重写旧项目。

## 三、共同接口与数据约定

### 3.1 `Project` 扩展

| 接口 | 行为与兼容要求 |
| --- | --- |
| `Project(state, *, base_dir=None)` | `base_dir` 只用于运行时路径解析，不写入状态；旧调用仍可用 |
| `Project.create(project_id, direction, *, base_dir=None)` | 保持原状态结构，设置运行时根目录 |
| `Project.load(path)` | 以状态文件父目录设置根；保留现有中断恢复行为，不自行落盘 |
| `Project.clone()` | 深拷贝状态并保留运行时根，替代会丢失根的 `Project(project.snapshot())` |
| `Project.version(artifact_id, version)` | 返回当前或历史指定版本的独立副本；缺失/无效版本报错 |
| `Project.add(id, kind, content, dependencies=(), *, files=())` | 保存文件引用；全部输入和依赖检查成功后才改变对象 |
| `Project.revise(id, content, reason, *, dependencies=None, files=None)` | 缺省沿用当前依赖/文件引用；显式值表示新版本绑定。变更前验证重复、不存在、自引用与循环依赖，失败不污染对象 |
| `Project.require_usable(id)` | 除原有状态及依赖检查，还核对当前版本关联文件的真实内容；旧 inventory 的 `input_path` 继续支持 |
| `Project.read_inventory_bytes(id)` | 读取并校验 inventory 实际输入；统一支持新 `input_ref` 与旧 `input_path`，返回 bytes |

新产物可有 `files` 列表，每项采用：

```json
{
  "scope": "project",
  "path": "literature/notes/paper-01/v0001.md",
  "sha256": "完整的64位十六进制文件摘要",
  "size_bytes": 128,
  "role": "literature_note"
}
```

上例说明字段类型，实际登记使用程序计算的摘要及字节数。`scope=project` 只接受项目内相对路径，拒绝 `..`、绝对路径及解析后逃出项目的符号链接；`scope=external` 只接受用户材料登记时明确提供的绝对路径，并标注其不包含在本地恢复包内。写入只发生在项目管理目录中。

状态中的 `completed/passed` 用于说明某份记录已生成且满足相应程序检查。文献的 `read_scope`、事实的 `evidence_status`、任务的 `task_status` 等另存业务字段，不能把“记录已保存”表述为“主张已证实”或“任务已完成”。

### 3.2 工作区接口

| 接口 | 输入/输出及具体行为 |
| --- | --- |
| `Workspace.create(root, project_id, direction)` | 建立不存在的用户项目，创建三个主目录和初始状态；存在内容时拒绝覆盖，返回 Workspace |
| `Workspace.open(root)` | 加载并检查已有状态，保留旧布局；失败时不创建另一项目、不覆盖原文件 |
| `Workspace.root` | 当前用户项目的规范化根路径，仅属于运行时上下文 |
| `Workspace.project` | 当前 Project；调用者通过已约定方法操作，不访问 `_state` |
| `Workspace.path(area)` | 返回登记的受控目录。area 为 `literature_sources/notes/evidence`、`data_raw/interim/processed/metadata`、`research_plans/tasks/decisions/sessions/code/runs/reports/drafts/history` |
| `Workspace.import_file(id, source, *, role, copy=True, reason)` | 导入来源；copy 为真时保存实际版本文件，外部索引则注明恢复依赖。返回已登记 source 产物 |
| `Workspace.save_record(id, kind, content, *, dependencies=(), reason)` | 调用记录契约，在新版本文件中保存 JSON/可读文本，随后保存状态，返回产物；已有标识显式修订 |
| `Workspace.save()` | 经检查保存状态，再生成进度视图；视图失败时返回状态已保存及视图失败的实际结果 |
| `Workspace.relocate_source(id, new_path, *, reason)` | 核对已登记内容与新位置，登记重新定位；源内容不同必须按新来源版本重新盘点 |
| `Workspace.audit(id, source_id, *, entity, time, numeric=())` | 用实际来源调用现有 `audit_csv`，附上 portable `input_ref` 和 source 依赖，记录完整报告；检查失败也保存证据 |

版本路径固定为来源或产物标识下的 `v0001`、`v0002` 等；标识采用 `[A-Za-z0-9_-]+`，展示标题可用中文。原文件名只取 basename。原始数据的每一批保存实际文件，检查点引用它们，不重复复制整套数据。

对用户旧布局登记路径映射，保留原 `reports/` 等路径。自动搬文件不属于 open 操作。已有 inventory 的绝对路径仍可读；新 Agent 路径必须经过统一解析，不再在各模块拼接本机路径。

### 3.3 研究记录

| kind | 关键字段 | 具体检查 |
| --- | --- | --- |
| `research_context` | `question`、`known`、`unknown`、`constraints`、`next_step` | 允许方向模糊；未知项不填造假答案 |
| `literature_evidence` | `source_id`、`read_scope`、`locator`、`claim`、`support`、`limits` | 阅读范围限定 metadata/abstract/excerpt/full_text；只有 metadata 时禁止填写经验发现；证据必须引用实际来源 |
| `concept_plan` | `question`、`goal`、`rationale`、`data_gaps`、`next_step` | 无数据也可保存；不能获得正式模型执行确认 |
| `session_note` | `summary`、`facts`、`decisions`、`outputs`、`open_questions`、`next_step`、`authorization` | 事实附来源种类和可见摘录/材料位置；没有平台标识时使用本地记录标识 |
| `user_decision` | `plan_id`、`plan_version`、`quote`、`scope`、`recorded_at` | 记录实际可见意见，引用具体计划与适用范围；保存摘录本身不自动批准计划 |
| `research_task` | `title`、`task_status`、`input_versions`、`outputs`、`next_step`、`blocked_reason` | task_status 为 queued/in_progress/waiting/needs_check/completed；等待说明原因，完成必须有有效实际产物 |

更正沿用同一事实/记录标识形成新版本，保留来源、原文与变更原因。输入版本是任务的依赖；任务产物作为版本引用存入 outputs，不把“任务 → 结果 → 任务”建成循环依赖。上游变化后任务记录过期，即使旧 `task_status` 为 completed，概览也显示需要重新核对。

### 3.4 检查点与恢复

定义 `create_checkpoint(workspace, label, reason)`、`compare_checkpoints(workspace, left, right)`、`restore_record(workspace, artifact_id, version, reason)`，放在 `econbiz/checkpoints.py`。

- 检查点包含状态快照、当时各产物版本及文件引用清单，保存到 `research/history/checkpoints/`，不依赖 Git。
- 检查点允许记录尚未完成的研究；清单逐项标明文件可访问/缺失/变化，不能把“不完整检查点”称为完整备份。
- 对比返回新增、修改、依赖变化及实际可恢复性；研究差异的解释由 Agent 结合具体内容提供。
- 恢复指定记录形成新修订，保留较晚历史和结果暴露记录。旧依赖版本与当前不符时停止自动恢复，列出需要重选或补齐的输入。
- 恢复正式方案后需重新适用方案检查与具体版本确认；不能复制旧确认来批准新版本。恢复普通记录只证明旧内容可读，不提升证据等级。

## 四、逐任务实施

### 任务 0：保存现有开发基线

**Files:** 审阅当前 `README.md`、`.gitignore`、`pyproject.toml`、`econbiz/`、`docs/`、`examples/`、`tests/`。保留被忽略的教学预览，不纳入基线。

- [ ] 重新检查 `git status --short --branch` 和 `git ls-files`，确认自本计划写成后没有其他任务新增变化。
- [ ] 运行完整既有测试。命令与预期：

```sh
python3 -m unittest discover -s tests -v
```

基线预期为 56 项通过；若已有其他合法新增测试，记录新计数及差异原因。

- [ ] 审阅明确目录后暂存；检查缓存、真实材料和教学预览未进入暂存区：

```sh
git add -- README.md .gitignore pyproject.toml econbiz docs examples tests
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
```

- [ ] 创建可恢复的本地基线提交：

```sh
git commit -m "chore: preserve research copilot foundation and agent-entry design"
```

- [ ] 检查当前隔离方式。新 worktree 必须基于这个完整提交，否则只会得到初始 README；是否使用 worktree 遵循用户偏好和宿主规则。新功能分支采用 `codex/` 前缀。此任务无需推送远程。

### 任务 1：统一文件引用和内容校验

**Files:** 新建 `econbiz/files.py`、`tests/test_files.py`；修改 `econbiz/state.py`、`econbiz/candidates.py`；扩展 `tests/test_state.py`、`tests/test_candidates.py`。

- [ ] 先写文件引用回归测试，覆盖相对路径、外部来源、逃逸、内容变化和丢失。以下测试代码放入 `tests/test_files.py`：

```python
import tempfile
import unittest
from pathlib import Path

from econbiz.files import describe_file, read_verified
from econbiz.state import WorkflowError


class FileTests(unittest.TestCase):
    def test_relative_reference_survives_folder_move_and_detects_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / '研究 项目'
            root.mkdir()
            source = root / 'input.csv'
            source.write_bytes(b'firm,year,x\na,2024,1\n')
            reference = describe_file(root, source, scope='project', role='raw_data')
            moved = root.rename(Path(folder) / '新的位置')
            self.assertEqual(read_verified(moved, reference), b'firm,year,x\na,2024,1\n')
            (moved / 'input.csv').write_bytes(b'firm,year,x\na,2024,2\n')
            with self.assertRaises(WorkflowError):
                read_verified(moved, reference)

    def test_project_reference_cannot_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'project'
            root.mkdir()
            source = Path(folder) / 'outside.csv'
            source.write_bytes(b'x\n1\n')
            with self.assertRaises(WorkflowError):
                describe_file(root, source, scope='project', role='raw_data')
```

- [ ] 运行 `python3 -m unittest discover -s tests -p 'test_files.py' -v`，确认失败原因是新接口未实现。
- [ ] 实现 `describe_file(root, path, *, scope, role)` 和 `read_verified(root, reference)`。前者解析受控路径、流式计算 SHA-256、记录字节数；后者先验证 scope、路径和实际内容再返回 bytes。路径校验拒绝项目外解析结果；文件系统错误转为含具体材料位置的 `WorkflowError`。
- [ ] 完成第 3.1 节 Project 扩展。`_validate()` 验证 files 类型/摘要/长度及历史条目；`require_usable()` 在消费时核对内容。`read_inventory_bytes()` 支持旧 `input_path`；所有新盘点优先使用 `input_ref`。
- [ ] 把 `candidates.py` 的直接 `Path(report['input_path']).read_bytes()` 改为 `project.read_inventory_bytes(inventory_id)`，把 `Project(project.snapshot())` 改为 `project.clone()`。
- [ ] 增加 Project 相对输入的保存/重载、旧绝对输入、复制后路径上下文不丢失测试；执行相关测试与全套原有测试，再提交本任务文件。

### 任务 2：三类目录和真实文件版本

**Files:** 新建 `econbiz/workspace.py`、`tests/test_workspace.py`；扩展 `econbiz/files.py`；修改 `econbiz/cli.py` 的建项与输出路径适配，保留旧接口。

- [ ] 在 `tests/test_workspace.py` 写建项与旧版恢复内容的测试：

```python
import tempfile
import unittest
from pathlib import Path

from econbiz.files import read_verified
from econbiz.workspace import Workspace
from econbiz.state import WorkflowError


class WorkspaceTests(unittest.TestCase):
    def test_import_versions_preserve_actual_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'study'
            source = Path(folder) / 'panel.csv'
            source.write_bytes(b'x\n1\n')
            workspace = Workspace.create(root, 'study', '教学项目')
            first = workspace.import_file('panel', source, role='raw_data', reason='第一批')
            source.write_bytes(b'x\n2\n')
            second = workspace.import_file('panel', source, role='raw_data', reason='新版导出')
            reopened = Workspace.open(root)
            old = reopened.project.version('panel', 1)
            self.assertEqual(read_verified(root, old['files'][0]), b'x\n1\n')
            self.assertEqual(read_verified(root, second['files'][0]), b'x\n2\n')
            self.assertEqual(first['version'], 1)
            self.assertEqual(second['version'], 2)
            for directory in ('literature', 'data', 'research'):
                self.assertTrue((root / directory).is_dir())
            with self.assertRaises(WorkflowError):
                Workspace.create(root, 'study', '不能覆盖')
```

- [ ] 运行 `python3 -m unittest discover -s tests -p 'test_workspace.py' -v`，观察新接口缺失导致的失败。
- [ ] 依第 3.2 节实现 create/open/path/import_file/audit。布局映射作为 `workspace_layout` 产物登记；仅创建三个主目录和当前操作需要的子目录。不可覆盖的版本文件写入前先计算内容与目标路径，若目标已经存在，只允许经校验的完全相同内容重试。
- [ ] 增加通用保存步骤：先在 Project 副本完成校验 → 写版本文件 → 原子保存状态 → 更新实例。此任务的保存回执说明 `state_saved=true`、`view_saved=false` 和“进度视图尚未接入”；阅读视图在任务 5 接入，不提前依赖不存在的 progress 模块。失败时保留可检查的孤立文件，原有状态仍然可用；重试不能把未登记文件当成已完成产物。
- [ ] 新 CSV inventory 绑定 source 版本，保存实际报告及 `input_ref`。结构错误的报告仍保存为 failed；新版来源使旧盘点与方案不能继续消费。
- [ ] 用 `unittest.mock.patch` 在状态保存前后注入 `OSError`，检查旧状态可读、孤立文件不会被自动登记；另测损坏状态不另建项目、旧 reports 布局可读、无效路径不写入。
- [ ] 原命令的用法保持兼容，新建项目输出遵循新布局；针对既有命令的测试修改仅用于验证路径变化，不删除原行为断言。运行全套测试并提交。

### 任务 3：检查点、比较和恢复

**Files:** 新建 `econbiz/checkpoints.py`、`tests/test_checkpoints.py`；扩展 `tests/test_workspace.py`。

- [ ] 在 `tests/test_checkpoints.py` 使用以下首个回归测试：

```python
import tempfile
import unittest
from pathlib import Path

from econbiz.checkpoints import create_checkpoint, compare_checkpoints, restore_record
from econbiz.workspace import Workspace


class CheckpointTests(unittest.TestCase):
    def test_restoration_creates_new_revision_without_erasing_later_history(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.csv'
            source.write_bytes(b'x\n1\n')
            workspace = Workspace.create(Path(folder) / 'study', 'study', '教学')
            workspace.import_file('data', source, role='raw_data', reason='首批')
            left = create_checkpoint(workspace, '初稿', '保存第一批')
            source.write_bytes(b'x\n2\n')
            workspace.import_file('data', source, role='raw_data', reason='第二批')
            right = create_checkpoint(workspace, '修改稿', '保存第二批')
            delta = compare_checkpoints(workspace, left['id'], right['id'])
            self.assertIn('data', delta['changed'])
            restored = restore_record(workspace, 'data', 1, '比较后恢复第一批')
            self.assertEqual(restored['version'], 3)
            self.assertEqual(workspace.project.version('data', 2)['version'], 2)
            self.assertEqual(len(workspace.project.snapshot()['history']['data']), 2)
```

- [ ] 运行 `python3 -m unittest discover -s tests -p 'test_checkpoints.py' -v`，先验证失败。
- [ ] 实现第 3.4 节三个接口。检查点 JSON 与其 SHA-256 单独写入不可覆盖目录；清单包含状态快照与文件核验结果。返回对象至少含 `id`、`path`、`file_status`；对比返回 `added/removed/changed/dependency_changes/file_status`。
- [ ] 恢复前读取实际旧文件并比较摘要及旧依赖。恢复调用显式 revise，不以旧 snapshot 替换当前状态，不删除结果历史或决定。恢复计划的状态保持 needs_decision。
- [ ] 错误注入覆盖：旧文件丢失、旧文件被篡改、外部来源失效、依赖版本不符、检查点写入中断；能保存“不完整”状态，但不能报告完整可恢复。
- [ ] 验证连续两个检查点未重复复制数据字节，恢复后的下游仍过期。运行相关和全套测试并提交。

### 任务 4：科研讨论、证据与确认摘录

**Files:** 新建 `econbiz/records.py`、`tests/test_records.py`；实现 `Workspace.save_record()`；新建手册 `project-records.md`。

- [ ] 建立第 3.3 节六种记录的合法/非法输入用例；每类至少覆盖一项会误导研究的缺失信息：文献没有实际来源、metadata 冒充全文发现、决定没有具体版本、摘要伪造平台标识、概念草案假造数据、完成任务无有效产物。
- [ ] 实现 `validate_record(kind, content, project)`：先复制为有限 JSON，逐项检查字段类型与非空文本、枚举值、来源版本和 outputs 引用，验证失败不修改 Project。未知 kind 拒绝登记；普通用户备注放入已定义记录的 notes 字段。
- [ ] 实现 `Workspace.save_record()`：每个版本同时保存结构化 JSON 与可读 Markdown；正文使用记录内容，文件路径按 kind 对应目录。程序格式检查通过时写明其检查范围，不能自动提高 `evidence_status`。
- [ ] 实际确认按以下顺序接入现有 approve，摘录路径由工具返回，不手填虚构路径：

```python
from econbiz.state import now

decision = workspace.save_record(
    'decision-001', 'user_decision',
    {'plan_id': 'plan-001', 'plan_version': 1,
     'quote': '按这份方案做', 'scope': 'plan-001 当前版本',
     'recorded_at': now()},
    reason='保存当前可见用户确认')
workspace.project.approve(
    'plan-001', '当前用户（对话确认，未作身份认证）',
    '已明确授权当前版本', decision['files'][0]['path'])
workspace.save()
```

其中 `recorded_at` 使用实际本地记录时间；`plan-001` 必须先用现有 `register_plan()` 登记且具备执行确认所需字段，任务 6 再扩展其证据与讨论依赖。普通讨论的赞同仅存记录，不调用 approve。

- [ ] 添加同一事实更正后旧文献解释/概念草案依赖过期测试；确认第一个版本仍可读，新会话能读到更正来源。
- [ ] 执行 `python3 -m unittest discover -s tests -p 'test_records.py' -v` 及全部既有测试，记录失败到通过，再提交。

### 任务 5：持续任务、科研进度和恢复入口

**Files:** 新建 `econbiz/progress.py`、`tests/test_progress.py`；扩展 `records.py` 和 Workspace 保存链。

- [ ] 增加测试：没有数据也能保存研究方向；会话摘要保存输出和授权范围；新 Agent 能读取最新更正；旧概览不覆盖有效状态；任务输入变化后已完成任务需复核；两个项目互不混用。
- [ ] 实现 `render_progress(project)` 返回 Markdown，`resume_context(workspace)` 返回可读结构化摘要；枚举事实、当前有效方案、任务/阻塞和下一步，消费前用实际材料校验，不把失败的数值结果渲染为已核对结论。
- [ ] 把任务业务状态与保存状态分别展示：例如“任务：等待字段说明；记录：已保存”。completed 任务校验有效 outputs，等待任务校验 blocked_reason；父级输入更新使已完成任务进入需要重新检查的展示状态。
- [ ] 保存进度视图失败时保持权威状态不回滚。测试使用以下故障注入结构，`render_progress` patch 的目标应是 Workspace 实际引用处：

```python
from unittest.mock import patch

before = workspace.project.snapshot()
with patch('econbiz.workspace.render_progress', side_effect=OSError('disk full')):
    receipt = workspace.save()
reloaded = Workspace.open(workspace.root)
self.assertEqual(reloaded.project.snapshot(), before)
self.assertTrue(receipt['state_saved'])
self.assertFalse(receipt['view_saved'])
```

`Workspace.root` 为规范化后的当前项目路径；Workspace.open 不依赖进度视图存在。

- [ ] 用户直接改概览时，用保存时记录的视图摘要发现改动；将其作为待核实用户输入展示并保留修改副本，再按实际明确意思登记，不直接写回权威状态。
- [ ] 为维护者提供可运行的保存/恢复 Python 示例，调用公共接口；每个示例在测试临时目录跑通。运行 `test_progress.py` 和全套测试并提交。

### 任务 6：Agent 方案入口及共同探索规则

**Files:** 新建 `econbiz/research_history.py`、`tests/test_research_history.py`；修改 `plans.py`、`candidates.py`、`state.py`；扩展 `tests/test_plans.py`。

- [ ] 将 `has_prior_results(project)` 原实现原样移到 research_history，并在 candidates 中导入，保持原公开导入路径可用；先运行原有候选方案测试验证未改变行为。
- [ ] 在 plans 中扩展下列接口，所有调用先校验再变更：

```python
register_plan(project, plan_id, content, inventory_id,
              evidence_ids=(), context_ids=())
revise_plan(project, plan_id, content, reason,
            inventory_id, evidence_ids=(), context_ids=())
```

函数接受未加新参数的旧调用。依赖仍须恰有一个 inventory，其他依赖为具体证据/讨论记录；不能把缺少数据的概念草案伪装为正式 plan。

- [ ] 实现共同 `prepare_plan_content(project, content)`：复制输入，检查项目全部结果与历史。如果在已有结果后新增或修订分析内容而未写有效 exploration_reason，拒绝登记；有理由时规范为 exploratory，保留原因；不改写研究目标或模型。确认操作核对已登记计划的提出/修订记录，不因确认当时已有结果而把此前未改变的计划重新归类；按既定授权重跑同样不改写原计划性质。
- [ ] 对通用 `Project.revise()` 的 plan 内容修订分支也调用共同校验，防止直接修订绕过探索规则。文件重新定位沿任务 2 的接口完成，不伪装成新研究设定。公共历史检查放在独立模块，避免 candidates 与 plans 循环导入。
- [ ] 使用原 `tests/test_plans.py` 的 `candidate()`，补以下测试方法：

```python
def test_agent_plan_after_results_keeps_exploration_history(self):
    self.p.add('result-1', 'result', {'coefficient': 0.0}, ['data'])
    self.p.mark('result-1', 'completed', 'passed', '教学结果记录')
    with self.assertRaises(WorkflowError):
        register_plan(self.p, 'new-plan', candidate(), 'data')
    content = candidate()
    content['exploration_reason'] = '查看结果后核实替代测量'
    register_plan(self.p, 'new-plan', content, 'data')
    self.assertEqual(self.p.artifact('new-plan')['content']['purpose'], 'exploratory')
```

- [ ] 覆盖证据修订→计划过期、依赖新增/删除、循环依赖拒绝、失败不污染对象、确认绑定具体版本；增加“结果前已登记且未改变的计划，在有其他结果后确认时仍保留原性质”测试，同时保留已存在的 DID 不降格和标准误选项检查。
- [ ] 更新旧 teaching candidate 路径，使其共用登记/探索逻辑，同时保留 comparison 依赖。运行 plans/history/candidates/state 测试及全套测试，提交。

### 任务 7：编写五个 Skills 与共用手册

**Files:** `AGENTS.md`、`CLAUDE.md`、五个 `.agents/skills/econbiz-*/SKILL.md` 及 assets，共享手册。

- [ ] 实施时先读取 skill-creator/writing-skills 的适用要求。用真实任务观察基线行为：含糊方向、论文证据、缺失值、继续项目、维护仓库；记录已有 Agent 是否会漏读材料或混淆任务，不用虚构转录冒充验证。
- [ ] 创建简短 AGENTS：开发/维护请求按开发任务处理；用户实际研究请求读取统一 Skill；只在确实开始研究时建项；明确数据事实、研究选择、现有授权、保存及恢复。CLAUDE 使用 `@AGENTS.md` 并定位同名项目 Skills。
- [ ] 五个 Skills 的发现描述使用自然任务语言，职责按设计第 4.5—4.7 节。主技能 frontmatter 起点为：

```yaml
---
name: econbiz-research
description: Use when the user starts, continues, or organizes an economics or business research project, including research progress, literature and data organization, decisions, and project versions.
---
```

- [ ] 各 Skill 正文包含“何时使用、先读哪些材料、如何判断与执行、实际输出、检查与信息不足处理”；research 负责保存/路由，专项技能处理方法。首版 analysis 只承诺当前已实现工具，interpret 对外部结果标明未复现。
- [ ] 实现六类模板：任务卡（research）、文献卡与判断—来源表（evidence）、候选方案比较（design）、分析与表图规划（analysis）、判断—结果表（interpret）、进度概览（research）。每个字段解释输入来源和未知处理；正式记录由公共接口保存。
- [ ] tool-contracts 手册为 create/import/audit/save_record/register_plan/approve/checkpoint/resume 各提供一段可复制的 Python 示例，示例先在临时目录实际执行，再写入文档。概念咨询示例不触发建项。
- [ ] teaching-cases 使用设计的三个情境，数值明确标注合成；记录当前能执行的检查及阶段 B 才能核对的估计，不填入预期显著性。
- [ ] 验证普通概念问答不会被强制建任务卡，用户选择内部 Skill 无需审批，实质研究选择沿已有授权规则处理。提交本任务文件；不把仅创建 SKILL.md 记成宿主已验证。

### 任务 8：双宿主打包和可移植性

**Files:** `scripts/sync_skills.py`、`.claude/skills/`、`tests/test_skills_package.py`、`tests/agent_cases/cases.json`。

- [ ] 写测试：五个维护源缺一报错；同名副本正文或 assets 差异报错；绝对本机路径/断链报错；不能把其他用户 Skill 当同步目标。
- [ ] 实现同步与检查两个模式，只处理明确列出的五个 econbiz Skill。同步使用普通文件复制，删除的旧资源仅在这些受管子目录内清理；其他 Skills 不动。检查模式不写入任何文件。
- [ ] 维护者运行：

```sh
python3 scripts/sync_skills.py
python3 scripts/sync_skills.py --check
python3 -m unittest discover -s tests -p 'test_skills_package.py' -v
```

同步后第二条应退出 0；人为改动临时副本后检查应非零并指出具体文件。用户 clone 后无需运行同步。

- [ ] 共享资源相对于工具仓库根解析；测试带中文和空格的复制目录。测试同时检查 AGENTS 与 CLAUDE 的入口引用，不用“含某句固定话”证明真实路由正确。
- [ ] 以 `cases.json` 保存行为案例的 id/request/input_fixture/expected_actions/prohibited_actions/required_artifacts，不存 API 密钥、不在工具仓库调用模型 API。
- [ ] 同步完成且静态检查通过后，提交两个宿主目录及检查脚本；真实宿主验证在任务 10 执行。

### 任务 9：可选的单项研究 Git

**Files:** `econbiz/research_git.py`、`tests/test_research_git.py`、`docs/research-handbook/project-records.md`。

- [ ] 所有测试使用临时父级工具仓库与子级研究项目。设置临时测试仓库身份，不读写用户全局 Git 配置。
- [ ] 定义 `enable_git(workspace, tracked_paths)` 与 `commit_changes(workspace, paths, message)`。路径必须属于当前研究且落在预先登记的跟踪范围；原始/大体积数据、论文全文和密钥不在默认范围。启用记录用户选择的范围；不自动添加 remote。
- [ ] 实现时显式校验 `git rev-parse --show-toplevel` 等于研究根。没有独立研究仓库时不得让 Git 向上发现并改动工具仓库。
- [ ] 提交使用参数数组和显式 cwd；message 作为单个参数，不拼接 shell。只暂存指定文件；发现已有暂存内容或同一文件的归属不明改动时返回可读冲突说明，不顺带提交用户其他修改。
- [ ] 测试未安装 Git/无身份的失败返回；研究文件历史仍可保存。禁止调用 push、remote add 或全局 config；拒绝越界文件；只读预览提交清单后再执行已有授权范围内的提交。
- [ ] 验证 Agent 仍从工具根加载入口。单独打开嵌套研究仓库的适配属于另行验证范围，说明中明确这个条件。
- [ ] 执行 `python3 -m unittest discover -s tests -p 'test_research_git.py' -v` 和全套测试，提交。

### 任务 10：集成、宿主实测与对外说明

**Files:** `tests/agent_cases/README.md`、`docs/agent-entry-validation.md`、`README.md`、`docs/development-guide.md`、`docs/design-and-development-standard.md`。

- [ ] 固定设计 v0.3 与当前实现提交；运行自动化测试和同步检查，保存真实命令、环境、计数及失败记录。
- [ ] 在单独的干净克隆中用已可用的 Codex 和 Claude Code 实测，不用本维护目录里的教学预览假冒用户研究。记录宿主版本、模型、系统、工具能力、读取 Skill 的证据及实际输出。
- [ ] 每个宿主至少测试：模糊方向、已有论文、CSV 合并/缺失问题、外部回归表、老师反馈、无数据概念草案、明确点名 Skill、跨阶段切换、开发仓库请求、缺少工具。
- [ ] 顺序接续测试：一方保存讨论、更正、方案与任务后结束写入，另一方读取同一项目；核对恢复的来源、有效版本及下一步。不得在两边同时写入。
- [ ] 文件恢复测试：创建两个材料版本和检查点，改坏最新文件、删除概览、模拟中断，分别核对可恢复范围和无法恢复的实际缺失。
- [ ] 对缺少的宿主/工具标记“未验证”并保留可复现步骤，继续完成独立可做的验收；不要仅为消除未验证标记捏造通过结论。
- [ ] 更新学生 README：自然语言使用步骤、首条请求示例、当前可用能力、文件位置和继续方法。开发命令与测试细节留在开发说明；原固定规则问答保留为内部教学工具。
- [ ] 将方法标准更新为注明 Agent 入口和阶段交付的下一版本，保持企业年度面板、正式计算范围、结果后探索及确认规则不变；旧标准变化在修订记录中说明。
- [ ] 至少邀请 3 名目标初学者完成短任务，记录理解问题、样本变化和续接的困难。无法当轮开展时如实记录未完成，不能宣称教学有效性已验证。
- [ ] 最终审阅发布文件与能力声明，再提交本批变更。推送由明确发布请求触发；Git 提交与自动化测试通过均不替代真实宿主行为验收。

## 五、失败与恢复规则

| 情况 | 实施必须保留的行为 |
| --- | --- |
| 旧状态损坏 | 保留原文件并报告定位，检查点恢复需核实内容；不另建同名项目掩盖失败 |
| 版本文件写入后状态保存失败 | 保留旧权威状态和孤立文件，返回未完成；重试先检查实际文件内容 |
| 状态保存后概览失败 | 报告状态保存成功、视图待重建；下次从状态生成 |
| 原材料变化或丢失 | 旧盘点、方案及下游不可继续消费，显示实际差异和需要补齐的材料 |
| 恢复版本的依赖不匹配 | 不绑定当前新版依赖冒充旧方案；列出需要重新选择的输入 |
| Agent 未发现 Skill | README 提供按项目入口读取的兜底提示，保留未自动加载的实测记录 |
| 缺少正式估计能力 | 能讨论、保存方案与阅读外部结果；状态不能写成已经执行/核验 |
| 多个研究项目、指代不明 | 先定位明确项目，不能混用另一研究的对话、数据或授权 |

## 六、设计覆盖检查

| 设计章节/要求 | 实施任务 |
| --- | --- |
| 第 1、3 节：维护与使用区分、clone 后入口 | 0、7、8、10 |
| 第 2、4.7 节：自然语言起点、自动选 Skill、继续 | 5、7、8、10 |
| 第 4.5、5 节：操作规程、研究指导与案例 | 6、7、10 |
| 第 6.1—6.4 节：目录、状态、科研记忆、顺序接续 | 1、2、4、5、10 |
| 第 6.5 节：六类模板 | 4、7 |
| 第 6.6 节：文件版本、检查点、恢复和 Git | 1—3、9、10 |
| 第 6.7 节：持续项目管理 | 4、5、7 |
| 第 7.1—7.2 节：接口、证据依赖和探索记录 | 1、2、4—6 |
| 第 7.3—7.5 节：正式分析、生成脚本与数值核验 | 阶段 B；A 中只写明能力限制与接口衔接 |
| 第 8 节：共享规范与参考项目借鉴 | 7、8；不引入参考仓库运行依赖 |
| 第 9—10 节：分阶段交付与实际验收 | 各任务回归检查、10 |

## 七、统一验证命令

下列命令在相应实现落地后运行；本次计划整理尚未生成同步脚本或新测试。

```sh
python3 -m unittest discover -s tests -v
python3 scripts/sync_skills.py --check
git diff --check
git diff --cached --check
```

程序测试检查路径、保存、依赖、确认和恢复；手工宿主验证检查实际任务理解、是否读取所需材料、是否如实说明当前能力。两类证据分别登记。只修文档的变更做结构/链接检查，不新增与正文逐字一致的脆弱测试。

## 八、实施进度记录方式

本计划复选框跟踪产品开发，不使用用户科研 `research_state.json`。每完成一个任务，补记实际改动文件、测试结果、提交标识和未完成条件，下一任务沿有效结果继续。

当前只完成实施前检查和本计划编写，任务 0—10 均未执行。最先开展任务 0，再依次实现 1—6；入口文件在工具契约可用后接入，避免写出无法执行的保存指令。

## 九、阶段 B 的交接范围

阶段 A 后另写正式执行闭环计划，沿本设计已确定的顺序完成，不计入本次 A 计划完成度：

1. **Excel/CSV 输入适配和分析样本。** 补充工作表、类型、文本代码、缺失语义、处理脚本与逐步样本计数；仍保留原始材料。
2. **单一 Python 描述/线性固定效应执行路线。** 固定实际依赖版本、支持的标准误与样本处理；独立参考检查固定效应吸收、秩、系数、标准误和置信区间。
3. **Agent 项目脚本运行包。** 执行前保存代码快照、方案与输入版本；保存实际参数、样本、环境、日志和结构化结果。模型偏离、错误连接与数值异常要能被检查发现。
4. **解释及修改后重跑。** 判断—结果表、报告数值来源、旧结果过期与按已授权方案重跑；完整保留不显著结果和结果后探索。

B 的具体统计实现与独立参考须在执行计划中选定、固定并验证；本次不提前宣称某个尚未接入的估计器可靠。A 可以先提供研究准备试用；只有 B 通过相应验收，才发布具有正式分析闭环的首版。
