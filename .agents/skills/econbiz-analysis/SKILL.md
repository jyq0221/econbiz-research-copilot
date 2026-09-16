---
name: econbiz-analysis
description: Use when the user needs to inspect economics or business data, understand missing values or merge losses, plan variable construction, check analysis inputs, or request statistical execution and replication.
---

# 数据检查与正式分析

## 先读与能力

先读实际数据说明、来源版本、方案及授权；盘点无需先有回归方案。读 [工具契约](../../../docs/research-handbook/tool-contracts.md) 和 [共同原则](../../../docs/research-handbook/principles.md)。
CSV 结构盘点仍可独立使用。阶段 B 已支持 Excel/CSV 适配、默认 Python 或可选 Stata 描述统计、企业/年度线性固定效应及独立数值复核；实际调用前读 [正式分析](../../../docs/research-handbook/analysis-execution.md)。Stata 当前仅验收 macOS arm64 / 19；DID、IV 等其他方法保留需求，不降格为普通关联回归。

## 执行与判断

先 import_file 保存原始字节，再 Workspace.audit；不覆盖原始数据。核实主体、期间、单位和时间口径，区分空白、未披露、不适用、匹配失败与零。
合并或样本流失先读输入、键和已有脚本，检查一对一/一对多关系及各步实际计数。没有计数就标未核实，不套教学数字。超出现有工具的处理先明确脚本与核验需求，不宣称完成。

正式运行用 execute_analysis(workspace, 新运行标识, 方案标识)。核实 analysis 依赖、execution 明确规则及当前批准版本，原授权适用时不重复确认。旧方案缺 execution 须先形成具体修订，不能猜测筛选条件。已授权方案内可以重跑，不覆盖旧运行。
默认 backend='python'，无 Stata 也能完成正式估计、独立 Python 复核、报告与重跑，不探测或要求安装 Stata。用户选择 Stata 时才用 backend='stata' 及实际入口，按手册核对环境；失败须说明，不能静默换引擎。两种正式引擎均由独立 Python 实现复核。相同当前批准方案和输入可用新运行标识、replication_of=原运行标识换引擎复现，不重复批准或自动改为探索。没有 Stata 仍可读取已保存的 Stata 结果，原生重跑需要匹配 Stata 环境。
查看返回的 execution_status/check_status、sample、result、verification 与日志，不能只看进程退出码。只有 completed/passed 才交给 write_result_report；失败/过期结果不可用于正式解释。自定义变量处理须保留代码和来源，当前固定运行器不自动认证任意处理脚本。

## 输出与检查

交付盘点、错误位置、样本/测量待核实事项及 [分析与表图规划](assets/analysis-plan.md)。失败仍保存报告，不自行填零、删样本或变量。
实质测量、样本和模型变化交 [design](../econbiz-design/SKILL.md) 形成可审阅选择；尊重已有授权。外部结果交 [interpret](../econbiz-interpret/SKILL.md) 作带来源的讨论。成功退出、生成代码或方案确认均不能登记为已估计或已独立核对。
