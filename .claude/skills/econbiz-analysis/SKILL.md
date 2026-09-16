---
name: econbiz-analysis
description: Use when the user needs to inspect economics or business data, understand missing values or merge losses, plan variable construction, check analysis inputs, or request statistical execution and replication.
---

# 数据处理、项目脚本与正式分析

## 先读与能力

先读实际数据说明、来源版本、方案及授权；盘点无需先有回归方案。读 [工具契约](../../../docs/research-handbook/tool-contracts.md) 和 [共同原则](../../../docs/research-handbook/principles.md)。
CSV 结构盘点仍可独立使用。分析请求先读 [项目分析工作流](../../../docs/research-handbook/project-analysis.md)：由 Agent 结合研究问题、字段含义和实际数据判断方法，完成处理、编程、运行、技术修错和交付。内置描述统计/固定效应的独立核验调用见 [正式分析](../../../docs/research-handbook/analysis-execution.md)。Stata 当前仅验收 macOS arm64 / 19。

## 执行与判断

先 import_file 保存原始字节，再 Workspace.audit；不覆盖原始数据。核实主体、期间、单位和时间口径，区分空白、未披露、不适用、匹配失败与零。
合并或样本流失先读输入、键和已有脚本，检查键关系、未匹配及各步实际计数。没有计数就标未核实，不套教学数字。缩尾、ln/log1p、比率、交互、标准化和滞后等用明确处理规则生成代码；保留原列、阈值、顺序及受影响数量。先检查对数定义域、零分母、缺失和断年，不能静默改口径。

先给简短的“推荐模型＋数据处理＋理由＋关键缺口”。已有授权就连续执行，不让用户填写参数表、选统计库或补写代码。常规路径、语法、依赖和列映射错误自动修复，每次新运行保存旧失败；改变变量含义、样本或识别策略且超出授权才请研究者决定。

内置方法外的需求，核对方法文档与环境，按明确的 project_script 方案用 save_project_script / execute_project_script 保存并执行项目代码。DID、IV、权重、多维聚类不能只留下“超范围待办”，也不能换成别的研究问题。缺识别信息时提具体缺口并完成独立可做的工作。代码必须使用实际路径与字段，不交付需要学生补写主体的占位脚本。

正式运行用 execute_analysis(workspace, 新运行标识, 方案标识)。核实 analysis 依赖、execution 明确规则及当前批准版本，原授权适用时不重复确认。旧方案缺 execution 须先形成具体修订，不能猜测筛选条件。已授权方案内可以重跑，不覆盖旧运行。
默认 backend='python'，无 Stata 也能完成正式估计、独立 Python 复核、报告与重跑，不探测或要求安装 Stata。用户选择 Stata 时才用 backend='stata' 及实际入口，按手册核对环境；失败须说明，不能静默换引擎。两种正式引擎均由独立 Python 实现复核。相同当前批准方案和输入可用新运行标识、replication_of=原运行标识换引擎复现，不重复批准或自动改为探索。没有 Stata 仍可读取已保存的 Stata 结果，原生重跑需要匹配 Stata 环境。
查看实际状态、样本、结果和日志，不能只看退出码。内置 result 只有 completed/passed 才交给 write_result_report。项目 script_run 成功仍为 completed/pending，write_script_report 提供“已执行、尚未独立数值复核”的说明；自写 passed 文件无效。数据处理复核与统计复核分别报告。按手册登记处理后输出和来源关系，不能把处理脚本成功当成回归数值通过。

## 输出与检查

交付盘点、错误位置、样本/测量待核实事项及 [分析与表图规划](assets/analysis-plan.md)。失败仍保存报告，不自行填零、删样本或变量。
实质测量、样本和模型变化交 [design](../econbiz-design/SKILL.md) 形成可审阅选择；尊重已有授权。外部结果交 [interpret](../econbiz-interpret/SKILL.md) 作带来源的讨论。成功退出、生成代码或方案确认均不能登记为已估计或已独立核对。
