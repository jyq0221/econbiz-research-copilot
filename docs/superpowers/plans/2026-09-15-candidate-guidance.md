# Candidate Guidance Implementation Plan

> **For agentic workers:** Execute inline with executing-plans; use an independent reviewer only for the completed code review required by requesting-code-review.

**Goal:** 把研究方向、已核实字段和真实样本事实连接为学生可读的候选方案草案。

**Architecture:** candidates.py 负责契约和确定性草案，guidance.py 负责问答，reports.py 负责安全静态报告。复用 Project、validate_plan 与 CSV 审计；不接入模型、外部服务或统计估计。

**Tech Stack:** Python 3.9+ 标准库、HTML、unittest。

---

- [x] 写 `tests/test_candidates.py`、`tests/test_guidance.py` 和 `tests/test_reports.py`，先运行观察因接口尚不存在而失败。
- [x] `econbiz/candidates.py`：实现 `build_candidates(project, inventory_id, brief)`，输入明细见阶段契约；输出 plans、questions、limitations、facts、recommendation；非法结构抛 WorkflowError，研究信息不足返回零方案及具体问题。
- [x] 复用 input_sha256 核对原始 CSV；共同样本前后分别计数；只用共同样本检查原始企业内变化；不执行数值估计。
- [x] `store_candidates(project, inventory_id, brief, prefix)`：保存完整 intake 和 comparison，方案以 inventory 与 comparison 为依赖，全部需确认；任何输入错误不得留下半个方案包。
- [x] `econbiz/guidance.py`：实现 `collect_brief(direction, columns, input_fn, output_fn)`；普通话提示、编号选列、跳过与待核实，禁止自动补全未知含义。
- [x] `econbiz/reports.py`：实现 `render_comparison(comparison)`；用户文本 HTML 转义、无外部资源、可读表格与后续问题，标明范围和快照。
- [x] 命令入口新增 `guide project --inventory ID` 与 `--brief FILE` 非交互方式；保存状态与 HTML；取消不保存；明确展示方案未经确认。
- [x] 合成样例增加完整字段说明；实跑 `guide --brief` 并阅读 HTML。补充学生说明、开发说明与第二阶段验收记录。
- [x] 跑全套 unittest、检查链接和补丁；独立审查并修复具体问题。
