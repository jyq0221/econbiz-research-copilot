# Framework Foundation Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task in the current session. No independent agents or external publication are needed.

**Goal:** 实现符合 v1.1 的本地状态、审计与研究方案关口基础框架。

**Architecture:** Python 核心负责确定性检查；状态和版本以 JSON 保存；命令行提供初始化、CSV 审计与状态入口。候选方案通过核心 API 登记，完整交互和数值估计为下一阶段。

**Tech Stack:** Python 3.9+ 标准库、unittest、CSV、JSON。

---

### Task 1: 约束测试先行

- [x] 创建 `tests/test_state.py`：验证未检查依赖不能消费、上游修订传递过期、旧版本保留、确认绑定版本、中断恢复及非法状态拒绝。
- [x] 创建 `tests/test_audit.py`：验证重复/空键、缺列、非有限值、原始缺失含义、字段盘点和输入哈希。
- [x] 创建 `tests/test_plans.py`：验证真实字段映射、方案必填项、方法边界、确认与可执行性。
- [x] 创建 `tests/test_cli.py`：临时目录内通过子进程运行初始化/审计/状态，重复初始化拒绝覆盖。
- [x] 运行 `python3 -m unittest discover -s tests -v`，确认因核心包尚不存在而失败。

### Task 2: 核心与存储

- [x] 创建 `econbiz/state.py`，提供 `Project.create`、`add`、`revise`、`mark`、`require_usable`、`approve`、`save`、`load`；每个修改留下事件时间与原因。
- [x] 数据结构固定为 `project_id`、`direction`、`schema_version`、`artifacts`、`history`、`decisions`、`events`；产物包含 `id`、`kind`、`version`、`content`、`dependencies`、`execution_status`、`check_status`。
- [x] 所有写入深拷贝输入；持久化禁止 NaN；重载验证引用和版本关系，running 产物转 failed。
- [x] 运行 `python3 -m unittest discover -s tests -p test_state.py -v`，要求全部通过。

### Task 3: 数据审计与候选契约

- [x] 创建 `econbiz/audit.py`：`audit_csv(path, entity, time, numeric)` 返回 `input_sha256`、`columns`、`rows`、`entities`、`periods`、`missing`、`numeric`、`issues`、`check_status`。
- [x] 创建 `econbiz/plans.py`：`register_plan(project, plan_id, content, inventory_id)` 校验方案并创建 needs_decision 产物；`require_approved_plan(project, plan_id)` 检查版本确认、数据审计及方法支持。
- [x] 运行对应测试，要求已知故障均有具体证据且禁止依赖错误数据继续。

### Task 4: 可运行入口与说明

- [x] 创建 `econbiz/__main__.py` 和 `econbiz/cli.py`，实现 `init`、`audit`、`plan`、`approve`、`status`；审计即使失败也保存报告并返回非零状态。
- [x] 创建 `examples/panel.csv` 和 `examples/candidate-plan.json`，标明全部为合成数据/教学方案。
- [x] 创建 `pyproject.toml`、`.gitignore`；补充 README 的操作方法、范围和下一步。
- [x] 运行全部 unittest；在临时目录实跑 `python3 -m econbiz init`、`audit`、`status`；运行 `git diff --check`。
- [x] 记录验收结果与尚未实现项，保持所有改动可本地审阅，不自动推送。

## 实际验收

32 项测试通过，合成 CSV 命令行流程已实跑；详见 `docs/foundation-validation.md`。原始标准文件保留。实现留在开发分支供本地审阅，未提交或推送。
