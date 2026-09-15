---
name: econbiz-research
description: Use when the user starts, continues, or organizes an economics or business research project, including research progress, literature and data organization, feedback, decisions, and project versions.
---

# 研究入口与接续

## 先读与适用范围

研究准备、继续项目、整理材料或老师反馈时使用。开发仓库请求返回开发任务；普通概念问答不建项。
先读用户请求和已有材料；已有项目用 Workspace.open、resume_context 核实有效记录和文件，再读本轮需要的内容。多个项目且指代不明时先定位，不混用数据或授权。
首次承担研究任务读 [共同原则](../../../docs/research-handbook/principles.md)；保存、恢复时读 [工具契约](../../../docs/research-handbook/tool-contracts.md) 和 [记录规则](../../../docs/research-handbook/project-records.md)。

## 判断与推进

按当前问题自动读取必要 Skill，不要求用户选择内部名称，不同时启动多个代理：

| 当前需要 | 读取 |
| --- | --- |
| 明确问题、测量或比较方案 | [design](../econbiz-design/SKILL.md) |
| 阅读论文、核实判断及来源 | [evidence](../econbiz-evidence/SKILL.md) |
| 检查数据、缺失和分析条件 | [analysis](../econbiz-analysis/SKILL.md) |
| 理解结果、比较解释或修改结果文字 | [interpret](../econbiz-interpret/SKILL.md) |

尊重用户点名的专项 Skill，跨环节按需顺序衔接。无数据也能讨论和保存 concept_plan，不能假造 inventory。
同一请求包含数据状态、缺失含义或处理规则，以及它们对研究方案的影响时，先读取 analysis 核实数据部分，再读取 design 比较研究选择。纯讨论也按所涉及的内容衔接，是否建项和保存仍由任务决定。
确实开始研究且位置明确时建立 Workspace，创建 literature/data/research，子目录按需生成。综合材料、形成方案或交付证据说明时用 [任务卡](assets/task-card.md) 明确输入、输出、检查和已有授权。

## 输出、保存和检查

交付对当前问题的判断、材料和有理由的下一步。重要更正沿同一记录标识修订，保留可见摘录、来源和原因。
实质工作结束保存 session_note、真实产物引用及任务状态；completed 必须有当前可用输出。检查回执及 [进度概览](assets/progress-overview.md)：状态失败不能说已保存，视图失败单独说明。
恢复时核对版本及真实文件；人工概览修改是待核实输入，不作为批准。缺工具时继续独立可做的讨论，说明结构化保存、检索或计算尚未完成。结束当前写入后再切换宿主。
