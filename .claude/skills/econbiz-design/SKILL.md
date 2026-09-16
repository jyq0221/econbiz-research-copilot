---
name: econbiz-design
description: Use when an economics or business researcher needs to clarify a question, choose measurements, compare candidate designs, or revise a research plan after feedback.
---

# 研究设计与方案比较

## 先读与判断

先读方向、有效文献证据、字段说明、盘点和决定，按 [共同原则](../../../docs/research-handbook/principles.md) 保持研究问题与测量边界。
区分描述、关联、因果、预测与尚未确定，说明竞争解释、指标代表什么、用什么比较回答问题。无数据时可以讨论，不要求学生先选模型。

## 执行与产物

缺理论或测量依据时读 [evidence](../econbiz-evidence/SKILL.md)，覆盖或变化不明时读 [analysis](../econbiz-analysis/SKILL.md)。
按真实条件给一个推荐方案和必要的替代方案，说明已核实条件与最小缺口。比较价值、测量、样本、条件和工作量，不按预期显著性排序，不从“未找到论文”推断创新。
综合研究目标、观察单位、结果变量性质、时间安排、可用变化和识别依据，分别决定模型、比较/识别策略、权重含义和标准误。DID 核对处理时间与比较组，IV 核对工具变量的研究依据；不凭相关系数自动挑工具，也不凭分布或显著性选模型。build_candidates 仅提供有界讨论草案，不是 Agent 的方法能力上限。
同时给出变量处理方案：哪些字段缩尾、分组与分位点，取 ln 的含义和定义域，缺失、合并及滞后如何处理。已有具体口径和执行授权就沿用；不机械要求用户再次选模型。方案确定后交 analysis 自动编写、实际运行并核对项目脚本，见 [项目分析工作流](../../../docs/research-handbook/project-analysis.md)。
用 [方案比较模板](assets/candidate-comparison.md) 给出推荐理由。未绑定数据用 concept_plan 保存；正式方案按 [工具契约](../../../docs/research-handbook/tool-contracts.md) 通过 register_plan/revise_plan 绑定有效 inventory、文献和讨论版本。

## 检查与决定

核对字段、年份、样本及标准误的研究理由。已有结果后新增或修改分析必须说明 exploration_reason，保留 exploratory 分类、原设定和全部结果。
确认前展示具体版本、选择影响和剩余问题。已有明确授权就保存摘录并沿用授权；草案同意不等于任意模型执行许可。结构检查和方案确认均不表示已经运行统计分析。
