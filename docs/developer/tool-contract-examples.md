# 开发验收：工具契约完整示例

以下八组示例已在临时合成项目按顺序执行。仅供完整源码仓库中的开发验收，不随使用 ZIP 分发。实际研究调用方式见 [Agent 工具契约](../research-handbook/tool-contracts.md)；不能复制示例授权或虚构文献内容。

普通概念咨询直接讨论，无需创建 Workspace。开始实际研究后再用这些保存接口；程序只核验字节、结构和引用，不认证经验主张。

## 1. 建立临时合成研究

```python
import json
import tempfile
from pathlib import Path
from econbiz.workspace import Workspace
from econbiz.files import read_verified
from econbiz.state import now
from econbiz.plans import register_plan, require_approved_plan
from econbiz.checkpoints import create_checkpoint, compare_checkpoints, restore_record
from econbiz.progress import resume_context

temporary = tempfile.TemporaryDirectory()
workspace = Workspace.create(Path(temporary.name) / "study", "synthetic", "合成数据演示")
assert all((workspace.root / area).is_dir() for area in ("literature", "data", "research"))
```

## 2. 导入实际文件

```python
source = workspace.import_file("panel", Path("examples/panel.csv"), role="raw_data", reason="导入合成演示数据")
paper_path = Path(temporary.name) / "paper.txt"
paper_path.write_text("合成材料：年度利润率表示水平，波动需要跨期定义。", encoding="utf-8")
paper = workspace.import_file("paper", paper_path, role="literature_source", reason="导入合成片段")
assert read_verified(workspace.root, source["files"][0]) == Path("examples/panel.csv").read_bytes()
```

## 3. 盘点与核查

```python
inventory = workspace.audit("inventory", "panel", entity="firm", time="year", numeric=["x", "y"])
assert inventory["content"]["rows"] == 9
assert inventory["check_status"] == "passed"
assert workspace.project.read_inventory_bytes("inventory") == Path("examples/panel.csv").read_bytes()
```

## 4. 保存证据、讨论和任务

```python
evidence = workspace.save_record("evidence", "literature_evidence", {
    "source_id": "paper", "read_scope": "excerpt", "locator": "合成片段第一句",
    "claim": "年度利润率水平不能直接表示波动", "support": "年度利润率表示水平，波动需要跨期定义。",
    "limits": "合成材料，只演示来源记录，不是实际文献结论"
}, reason="保存已读片段")
context = {"question": "合成指标如何比较", "known": ["企业年度数据"],
           "unknown": ["真实测量依据"], "constraints": ["仅演示"], "next_step": "审阅方案"}
workspace.save_record("context", "research_context", context, reason="记录当前问题")
workspace.save_record("session", "session_note", {
    "summary": "核实合成材料含义",
    "facts": [{"id": "fact-1", "claim": "水平与波动需区分", "source_kind": "source_excerpt",
               "locator": "paper 第一行", "excerpt": "年度利润率表示水平",
               "evidence_status": "source_supported", "source_ref": {"artifact_id": "paper", "version": 1}}],
    "decisions": [], "outputs": [{"artifact_id": "evidence", "version": 1}],
    "open_questions": ["真实数据的指标定义"], "next_step": "比较方案",
    "authorization": "当前仅为临时合成测试，不代表真实研究授权"
}, reason="保存可核对摘要")
workspace.save_record("task", "research_task", {
    "title": "核实合成片段", "task_status": "completed", "input_versions": {"paper": 1},
    "outputs": [{"artifact_id": "evidence", "version": 1}], "next_step": "方案讨论", "blocked_reason": ""
}, reason="实际证据卡已保存")
```

## 5. 正式方案登记

```python
content = json.loads(Path("examples/candidate-plan.json").read_text("utf-8"))
plan = register_plan(workspace.project, "plan", content, "inventory",
                     evidence_ids=["evidence"], context_ids=["context"])
workspace.save()
assert plan["execution_status"] == "needs_decision"
assert workspace.project.snapshot()["decisions"] == []
```

## 6. 绑定具体版本的确认摘录

```python
decision = workspace.save_record("decision", "user_decision", {
    "plan_id": "plan", "plan_version": 1, "quote": "【合成测试授权】按这份方案做",
    "scope": "只测试临时合成项目 plan v1", "recorded_at": now()
}, reason="验证具体版本确认，不用于真实研究")
workspace.project.approve("plan", "合成测试用户（未作身份认证）", "验证授权绑定",
                          decision["files"][0]["path"])
workspace.save()
assert require_approved_plan(workspace.project, "plan")["version"] == 1
# 确认是状态测试，没有执行统计估计。真实任务只能保存当前用户实际可见的确认。
```

## 7. 检查点、比较和旧版恢复

```python
left = create_checkpoint(workspace, "初稿", "保存当前材料与状态")
workspace.save_record("context", "research_context", dict(context, question="修订后的合成问题"),
                      reason="演示更正")
right = create_checkpoint(workspace, "更正稿", "保存更正后的状态")
difference = compare_checkpoints(workspace, left["id"], right["id"])
assert "context" in difference["changed"]
restored = restore_record(workspace, "context", 1, "比较后恢复初稿内容")
assert restored["version"] == 3
assert workspace.project.version("context", 2)["content"]["question"] == "修订后的合成问题"
assert read_verified(workspace.root, restored["files"][0])
```

## 8. 保存与新会话接续

```python
receipt = workspace.save()
assert receipt["state_saved"] and receipt["view_saved"]
reopened = Workspace.open(workspace.root)
summary = resume_context(reopened)
assert summary["project_id"] == "synthetic"
assert summary["records"]["context"]["version"] == 3
# 不依赖宿主聊天记录；手动删除概览也可从状态重建。
temporary.cleanup()
```

## 失败与范围

- import_file 默认复制实际材料；copy=False 只接受明确绝对路径，恢复依赖外部文件。用途为 raw_data/literature_source/data_metadata/external_result/research_material。
- audit 即使结构失败也保存报告，检查 check_status 和 issues；失败盘点不能登记正式方案。
- save_record 支持六种记录，字段见 [记录规则](../research-handbook/project-records.md) 与 econbiz/records.py。修订沿原标识，理由必填。方案修订使用 revise_plan，并重新绑定文献/讨论输入。
- Project 的 add/revise/clone/version/read_inventory_bytes 可直接使用；需要保存持久文件时优先通过 Workspace。不要访问或修改 _state。
- 保存接口抛 WorkflowError 或 OSError 时保留旧状态和孤立文件，先检查错误位置；不另建同名项目。save 返回 state_saved/view_saved，import/audit/save_record 的后续视图回执在 workspace.last_receipt。
- 确认摘录只记录可见用户意见；approve 绑定具体版本并校验已登记摘录。旧式自由文本 evidence 仅为兼容调用者陈述，不是身份认证或自动读取聊天记录。
- require_usable 会检查真实文件、依赖和任务/摘要输出版本；不能仅看 completed 字段。结果恢复后仍待核验；外部结果登记也保留结果暴露，后续新分析需说明探索原因。
- 比较检查点会重新检查实际文件；complete=false 的检查点不是完整本地备份。恢复旧依赖不匹配时停止，旧版方案恢复需重新确认。
- 用户研究 Git 为可选：enable_git(workspace, tracked_paths) 登记范围；preview_changes(workspace, paths) 只读列出文件；commit_changes(workspace, paths, message) 仅在既有授权范围内本地提交。当前工具限每个不超过 1 MiB 的 UTF-8 代码、文字和元数据，原始数据/全文/运行包不纳入。已有暂存或缺身份会拒绝，不改全局身份，不设置远端。
