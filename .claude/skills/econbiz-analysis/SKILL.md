---
name: econbiz-analysis
description: Use when the user needs to inspect economics or business data, understand missing values or merge losses, plan variable construction, check analysis inputs, or request statistical execution and replication.
---

# 数据检查与分析准备

## 先读与能力

先读实际数据说明、来源版本、方案及授权；盘点无需先有回归方案。读 [工具契约](../../../docs/research-handbook/tool-contracts.md) 和 [共同原则](../../../docs/research-handbook/principles.md)。
阶段 A 可检查 UTF-8 CSV 的键、重复、缺失标记和数值合法性。正式描述统计、固定效应估计、Excel 适配与生成脚本的正式运行包属于阶段 B；保留这些需求，但说明当前未执行。

## 执行与判断

先 import_file 保存原始字节，再 Workspace.audit；不覆盖原始数据。核实主体、期间、单位和时间口径，区分空白、未披露、不适用、匹配失败与零。
合并或样本流失先读输入、键和已有脚本，检查一对一/一对多关系及各步实际计数。没有计数就标未核实，不套教学数字。超出现有工具的处理先明确脚本与核验需求，不宣称完成。

## 输出与检查

交付盘点、错误位置、样本/测量待核实事项及 [分析与表图规划](assets/analysis-plan.md)。失败仍保存报告，不自行填零、删样本或变量。
实质测量、样本和模型变化交 [design](../econbiz-design/SKILL.md) 形成可审阅选择；尊重已有授权。外部结果交 [interpret](../econbiz-interpret/SKILL.md) 作带来源的讨论。成功退出、生成代码或方案确认均不能登记为已估计或已独立核对。
