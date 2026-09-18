---
name: econbiz-interpret
description: Use when the user asks to explain regression results, compare findings, understand uncertainty or non-significant estimates, respond to research feedback, or revise result text.
---

# 结果解释与研究表达

## 先读与判断

先读事前问题、实际表格、代码或运行记录、变量单位/变换、样本和诊断，核实文件及版本。用户回归表标为“外部结果，尚未复现”，以 external_result 来源登记；新增 Python 执行能力不自动认证外部 Stata 表。
按 [共同原则](../../../docs/research-handbook/principles.md) 区分方向与幅度、精度、设定差异和解释层级。没有区间或样本就不补造；不显著不等于没有关系，精度不足与相反证据分别解释。

## 执行与产物

先用 [判断—结果表](assets/judgment-results.md) 连接事前判断、实际证据和解释范围，再写结果段落。用单位和具体比较帮助理解；不同设定同时改变样本时不能全归因于控制变量。
本项目正式结果先 project.require_usable，再按 [正式分析](../../../docs/research-handbook/analysis-execution.md) 用 write_result_report 生成可追溯表格和解释。需要 completed/passed 的实际运行及独立核验；数值核验不认证因果假设，报告文件本身也不保证仍为当前版本。
项目脚本的真实输出可以按 [项目分析工作流](../../../docs/research-handbook/project-analysis.md) 讨论，并明确“已执行、尚未独立数值复核”；读 script_run 的文件、日志与实际样本，不能把这类输出写成内置已复核结果。分别说明执行检查、处理核对和统计复核；任何脚本自报 passed 都不是独立数值认证。
需来源时读 [evidence](../econbiz-evidence/SKILL.md)，需核实计算时读 [analysis](../econbiz-analysis/SKILL.md)。后续新问题交 [design](../econbiz-design/SKILL.md) 保存为结果后探索，不为显著性遍历设定。

## 检查与收尾

多模型比较、基准/稳健性并列表和 Word 交付先读 [结果交付手册](../../../docs/research-handbook/result-delivery.md)。沿用实际模型角色与顺序，按变量定义对齐，核对真实样本键；整理现有结果不重跑分析。使用 write_model_comparison / write_word_report 保存版本，DOCX 内容核对、实际渲染与逐页视觉检查分别记录。缺少渲染不能宣称版式通过；未核验脚本不混入正式比较列。新会话用 read_model_comparison / read_word_report 核对有效材料。

LaTeX、公式或 PDF 交付先读 [LaTeX 结果交付](../../../docs/research-handbook/latex-delivery.md)。单个已核验运行用 run_id，已有比较用 comparison_id；用 write_latex_report 保存源文件，compile_latex_report 实际编译。公式须绑定真实方案或笔记，说明中的数字先核对。源码、编译与逐页视觉状态分别记录；缺引擎保留源码及失败原因，不能声称 PDF 已生成。接续时调用对应的 read_latex_report / read_latex_build / read_latex_review。

核对数值、方向、样本、单位和来源；系数、标准误、区间本身不能证明因果。保留合理设定及全部结果。
工作记录与成稿分开，待办和占位不混入结果文字，不自动扩展为整篇论文。按 [工具契约](../../../docs/research-handbook/tool-contracts.md) 保存外部来源、带出处的 session_note 和真实输出，说明核对到哪一步及下一步理由。
