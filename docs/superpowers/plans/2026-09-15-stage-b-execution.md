# 阶段 B：Python 正式执行与独立复核实施计划

> **For agentic workers:** 使用 subagent-driven-development；按下列复选步骤实施、检查规格及代码质量。用户已于 2026-09-15 指令开始实施，沿已确认设计推进。

**Goal:** 将已确认的企业年度面板方案连接到真实 Python 描述统计、线性固定效应执行、独立数值复核、可重跑运行包和结果解释。

**Architecture:** 沿用 Workspace/Project 单写入者及文件版本链。输入适配和可执行方案明确数据处理规则；运行前冻结输入、方案、执行代码和环境，独立进程运行；固定复核接口重算关键数值，结果及解释只有通过核验才能消费。统计主路径为 linearmodels PanelOLS，参考路径使用 SciPy 稀疏固定效应投影与独立最小二乘及协方差公式。

**Tech Stack:** Python 3.9+；分析可选依赖锁定本机已安装版本：numpy 2.0.2、scipy 1.13.1、pandas 2.3.3、linearmodels 6.1、openpyxl 3.1.5、statsmodels 0.14.6。阶段 A 保留无第三方依赖的使用方式。

## 既定设计细化与边界

- 维护位置沿用户 AGENTS.md 使用 codex/framework-foundation；工作区原先干净。108 项基线测试通过。不改 main，不对外发布。
- 主范围为 description/descriptive 与 association/linear_fe。固定效应限已盘点的企业、年度字段的一项或两项；支持 classical、HC1、单维 cluster。不实现 Stata、DID、IV、权重、多维聚类或自动模型搜索。
- 内置可执行 `execution` 字段随方案版本确认：`sample_filters`（eq/ne/in/ge/le）、`missing: complete_case`、`singleton: keep`、`confidence: 0.95`。没有这一字段的旧方案可以讨论，正式执行须修订并重新确认。字段名、变量规则不从自然语言猜测。
- CSV 保留文本代码与原始缺失标记；XLSX 显式选择工作表，不执行公式、不猜测数值单元格的前导零。转为登记的 CSV 后继续共用盘点/方案接口。
- 每次运行生成自己的 `run.py` 与工具源码快照。项目特有变量处理可由 Agent 编写脚本，产出经过登记、盘点并绑定方案的数据；首版正式执行入口固定，不执行任意未核验第三方脚本。
- 固定效应标准误显式计入全部设计秩；HC1 乘 n/(n-K)，cluster 乘 G/(G-1)*(n-1)/(n-K)。双向不连通面板拒绝并给出诊断，避免自由度误算。单例保留并报告。区间及双侧 p 值使用 t 分布，聚类 G-1、其他 n-K。完全吸收/共线/零残差或非有限推断停止正式解释。
- 复核重新构造参考模型，不复用主估计对象；核对样本、秩、系数、标准误、p 值、区间和描述统计。容差预先固定 rtol=1e-6、atol=1e-8；超差记录失败。数值通过不等于推断假设或因果识别通过。

## Task 1：纯统计执行与独立参考（独立子任务）

**Files:** 新建 `econbiz/estimation.py`、`econbiz/numerical_check.py`、`tests/test_estimation.py`。

- [x] 先编写失败测试：已知斜率的平衡/非平衡企业年度面板；三种标准误；控制变量；单向固定效应；完全吸收、共线、一簇、非有限值、不连通面板、数值被修改。
- [x] 执行 `python3 -m unittest discover -s tests -p test_estimation.py -v`，确认缺失功能的失败。
- [x] 实现纯接口 `estimate(rows, spec)`，rows 为已完整案例筛选的字符串字典列表；spec 为 `{model, y, x, fixed_effects, entity, time, standard_errors, confidence}`，其中 x 为核心变量加控制变量列表。返回 JSON 数值、描述统计、实际设定、观测键和诊断。
- [x] 实现 `verify_numerics(rows, spec, result)`，重建参考计算，返回 passed/failed、容差、逐字段偏差、参考来源和覆盖范围；不得将重复主函数调用作为独立核验。
- [x] 验证主路径实际估计选项、样本与返回元数据一致；用故意修改系数/标准误/键的结果验证复核会失败。
- [x] 阅读源码作规格检查，修正后由另一审阅者进行数值与代码质量检查。

## Task 2：输入适配与执行方案

**Files:** 新建 `econbiz/analysis_input.py`、`econbiz/execution_spec.py`、`tests/test_analysis_input.py`、`tests/test_execution_spec.py`；通过模块公共函数接入现有 Workspace，不重复增加包装方法。

- [x] 失败测试覆盖文本代码、XLSX 指定工作表/公式/错误值/数字格式、缺失语义、重复键、过滤、逐步样本损失及未知执行选项。
- [x] `import_table(workspace, artifact_id, source_id, *, sheet=None)` 从已登记来源读取，生成保留原始值的 CSV 与转换说明，依赖来源版本。
- [x] `compile_spec(plan, inventory)` 严格校验有限选项并转成统计接口参数；`prepare_sample(raw, spec)` 返回实际行与逐步样本审计。
- [x] 过滤规则与完整案例逐列记录剔除数、剩余数和观测键；非法数值不是缺失，不自动填零或去重。
- [x] 运行两个专门测试文件，确认全部通过。

## Task 3：正式运行与恢复

**Files:** 新建 `econbiz/execution.py`、`econbiz/run_worker.py`、`tests/test_execution.py`；调整 `econbiz/research_history.py`（如需）与 `pyproject.toml`。

- [x] 失败测试覆盖未确认、输入修改、旧方案、执行失败、重跑、过期、输出篡改、独立核验失败和新进程复现。
- [x] `execute_analysis(workspace, run_id, plan_id)` 先检查批准版本、盘点真实字节及分析环境，冻结运行包，登记 running；子进程只读取冻结输入与方案，写入本次输出。
- [x] 保存 plan.json、input.csv、spec.json、工具源码快照、run.py、环境版本、样本链、结果 JSON、核验 JSON、stdout/stderr 与代码 SHA-256。
- [x] 完成后保存 kind=result，分别设置 execution_status/check_status。失败有日志且不能用于正式解释；中断后 Workspace.open 沿现有规则处理。每次重跑使用新运行标识，拒绝覆盖。
- [x] 每次正式运行自动做独立数值核验，检查实际模型与方案相符；在 run package 内通过独立 Python 进程重新运行以验证可复现性。
- [x] 固定可选依赖；未安装分析依赖时旧阶段 A 操作仍能用，正式执行给出明确安装指引。

## Task 4：结果表、解释与用户入口

**Files:** 新建 `econbiz/result_report.py`、`tests/test_result_report.py`、`docs/research-handbook/analysis-execution.md`；更新 README、三份手册及 `.agents/skills/` 相关入口，同步 `.claude/skills/`。

- [x] 失败测试覆盖未核验/过期结果拒绝消费、数值与表格一致、不显著结果仍完整呈现、方案判断/单位/来源齐全。
- [x] `write_result_report(workspace, report_id, run_id)` 只消费当前可用结果，生成中文 Markdown/HTML、CSV 回归表和判断—证据数据，绑定结果依赖。
- [x] 解释方向、每单位系数、区间、样本、固定效应及标准误；保留不显著结果，不自动宣称无关系或因果效应。
- [x] 更新维护文档和学生入口，给出完整公共接口例子及真实能力边界。脚本依赖版本、方法公式和参考来源写入开发说明。

## Task 5：端到端验收与交付

**Files:** 新建 `docs/stage-b-validation.md` 与指导案例测试；更新本计划复选记录。

- [x] 临时合成项目实跑：导入→盘点→候选方案→修订可执行字段→确认→回归→复核→报告→修改变量→旧结果过期→重新确认与重跑→新进程复现。
- [x] 注入错误：完全吸收、样本损失、输入/输出变化、未确认方案及数值不一致均被捕获。将测试证据和方法覆盖范围写入验收记录。
- [x] 完成独立规格审阅，修复发现；再完成独立代码质量/数值审阅，修复发现。
- [x] `python3 -m unittest discover -s tests -v`、`python3 scripts/sync_skills.py --check`、`git diff --check`；检查真实归档依然包含所需运行手册/代码。
- [x] HTML 结果进行浏览器渲染检查。记录程序验收，不冒称 Stata、跨宿主或真实初学者试用通过。
- [x] 在开发分支保留完整可审阅变更，报告完成范围、测试、限制与位置；未经明确发布请求不更新 main 或 GitHub。

## 实际完成记录

全部五项已完成。151 项测试通过，独立数值/质量审阅及 Skills 实际会话与浏览器渲染检查完成。错误收尾新增 Project.finish_result；接收方再次独立计算并保存 parent-verification.json。详细证据及未覆盖范围见 [阶段 B 验收](../../stage-b-validation.md)。
