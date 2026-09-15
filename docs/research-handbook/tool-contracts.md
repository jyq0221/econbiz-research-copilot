# Agent 工具契约

从工具项目根调用 `econbiz` 公共 Python 接口。研究路径、材料位置、字段含义、记录内容和授权均来自本轮实际任务；普通概念咨询无需建项。

以下是调用片段，变量由实际材料确定，不是无需输入即可顺序执行的演示脚本。默认 clone 和 ZIP 不附合成数据；完整的合成验收流程保存在[开发分支的示例](https://github.com/jyq0221/econbiz-research-copilot/blob/codex/framework-foundation/docs/developer/tool-contract-examples.md)。

## 1. 定位、建立或继续研究

`project_root` 是明确的研究目录；`project_id`、`direction` 来自当前任务。新研究使用 `Workspace.create`，已有研究使用 `Workspace.open`，两者按实际状态选择。存在但损坏的状态不是新项目。

```python
from pathlib import Path
from econbiz.workspace import Workspace
from econbiz.progress import resume_context

# 仅在明确建立新研究时调用：
workspace = Workspace.create(Path(project_root), project_id, direction)
```

已有研究先打开并核对有效材料、待办及授权，不依赖前轮聊天：

```python
workspace = Workspace.open(Path(project_root))
summary = resume_context(workspace)
```

## 2. 导入实际来源

`source_id` 标识这份材料，`input_path` 必须是已定位的实际文件。默认复制真实字节并保留版本；同标识更新需说明理由。`role` 可用 raw_data、literature_source、data_metadata、external_result、research_material。

```python
source = workspace.import_file(source_id, Path(input_path), role=role, reason=reason)
receipt = workspace.last_receipt
```

`copy=False` 只用于明确选择的绝对路径外部索引，其恢复仍依赖原文件。重新定位用 `relocate_source` 校验相同内容。外部回归表以 external_result 登记并注明未复现。

## 3. CSV 结构检查

读取实际文件后确定企业列 `entity_column`、时间列 `time_column` 和经确认的数值列 `numeric_columns`。字段名不证明经济含义，不默认填零或去重。

```python
inventory = workspace.audit(inventory_id, source_id, entity=entity_column,
                            time=time_column, numeric=numeric_columns)
report = inventory["content"]
receipt = workspace.last_receipt
```

错误报告同样保存。检查 `check_status`、`issues`、`partial` 和实际样本信息；失败或过期盘点不能登记正式方案。读入材料时可用 `read_verified(workspace.root, reference)` 核对真实字节，不仅检查文件是否存在。

## 4. 记录事实、讨论与任务

六种记录及来源规则见 [记录说明](project-records.md)，完整字段契约可读取 [records.py](../../econbiz/records.py)。`content` 必须根据实际材料组织；未知保持未知，文献 metadata 不填写经验发现。

```python
record = workspace.save_record(record_id, kind, content, reason=reason)
receipt = workspace.last_receipt
```

同一事实更正沿相同 `record_id` 修订，保留出处及修改原因；新版本会使受影响记录过期。任务和会话摘要的 `outputs` 使用实际 `{artifact_id, version}` 引用。任务 completed 需当前可用产物；等待任务注明 blocked_reason，业务状态与保存状态分别表达。

## 5. 登记或修订方案

无数据草案用 concept_plan 保存；正式方案使用实际 inventory 及文献、讨论依赖。内容字段和支持范围见 [plans.py](../../econbiz/plans.py)，不能为符合后端能力改写研究目标。

```python
from econbiz.plans import register_plan, revise_plan

plan = register_plan(workspace.project, plan_id, plan_content, inventory_id,
                     evidence_ids=evidence_ids, context_ids=context_ids)
receipt = workspace.save()
```

修订使用 `revise_plan(..., reason=实际修改理由)`，重新绑定适用的数据和证据版本。已有结果后新增或修改设定必须记录 exploration_reason，并标为 exploratory；保留原方案及结果。登记方案不等于批准或执行。

## 6. 保存真实确认并绑定版本

只有用户当前可见授权适用于具体方案版本时才使用确认接口；已有明确授权不重复审批。`decision_content` 必须包含 plan_id、plan_version、quote、scope、recorded_at，摘录使用真实原话及实际记录时间，不编造身份或平台消息标识。

```python
decision = workspace.save_record(decision_id, "user_decision", decision_content,
                                 reason=decision_reason)
workspace.project.approve(plan_id, actor, approval_reason, decision["files"][0]["path"])
receipt = workspace.save()
```

先核对决定记录已保存，再使用返回路径确认。摘录本身不自动批准；确认不表示统计分析已执行或复现。旧式自由文本 evidence 只是兼容调用者声明。

## 7. 检查点、比较与恢复

```python
from econbiz.checkpoints import create_checkpoint, compare_checkpoints, restore_record

checkpoint = create_checkpoint(workspace, label, reason)
difference = compare_checkpoints(workspace, left_checkpoint_id, right_checkpoint_id)
restored = restore_record(workspace, artifact_id, old_version, restore_reason)
```

检查点记录状态、版本和实际文件核验范围，不重复复制所有原始数据。`complete=false` 不表示完整备份。恢复前核对旧字节及依赖；恢复形成新修订，不抹去后续历史。旧方案恢复需重新确认，旧结果恢复仍待数值核验。

## 8. 保存回执与收尾

```python
receipt = workspace.save()
reopened = Workspace.open(workspace.root)
summary = resume_context(reopened)
```

核对 `state_saved`、`view_saved` 与可能的 `view_error`，再向用户说明实际保存结果。重要更正及时保存，结束实质工作时保留 session_note、真实输出和下一步。

## 失败处理和可选 Git

- Workspace 先写不可覆盖的版本文件，再原子保存状态，最后更新概览。状态保存失败时旧状态有效，孤立文件等待核实；概览失败不回滚状态。捕获 WorkflowError / OSError 后检查实际位置，不另建同名项目或伪称成功。
- `require_usable` 会核验真实文件、依赖及输出版本；不能仅凭 completed/passed 消费记录。人工概览更正另存为待核实输入，不直接成为事实或批准。
- Project 的 add/revise/clone/version/read_inventory_bytes 可按公共契约调用；持久文件操作优先用 Workspace，不修改私有 `_state`。同一研究保持一个写入者。
- 可选研究 Git 使用 `enable_git(workspace, tracked_paths)` 登记范围，先 `preview_changes`，再按已有授权 `commit_changes`。范围、身份、文件限制及无远端操作规则见 [记录说明](project-records.md)。
