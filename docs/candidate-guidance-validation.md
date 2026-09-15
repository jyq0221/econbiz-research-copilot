# 引导式方案阶段验收

日期：2026-09-15。依据：已确认的设计标准 v1.1。此阶段只完成固定规则的引导式草案，不代表完整研究助手已完成。

## 已验证

- 全套 56 项测试通过，覆盖原有框架与新增功能（包括旧状态文件的结果历史兼容）。
- 使用 9 行、3 个企业的合成 CSV 实跑初始化、盘点和方案准备：关注指标可用 9 行，两指标共同可用 8 行，报告说明因解释指标缺失进一步减少 1 行。
- 生成两条回答不同问题的路线：描述关注指标，以及讨论两个指标的条件关联。全部方案保留为待确认，真实演示未写入研究者确认。
- 已在本地浏览器检查中文阅读效果与窄窗口排版，教学报告保存为 `examples/student-report.html`；全部数据与测量说明均明确标为合成演示。
- 独立审查指出的历史结果探索分类丢失、报告遗漏探索标记与原因均已加入回归测试并修复。

## 对应测试

| 行为 | 证据 |
| --- | --- |
| 因果、预测、未确定目标不自动改为关联 | `test_unsupported_or_unknown_goal_preserved_without_downgrading` |
| 未知字段不编造，未核实含义不当成确认 | `test_absent_field_rejected_without_mutating_project`、`test_unconfirmed_or_missing_meaning_no_fabrication` |
| 支持零条、一条、两条路线 | `test_no_usable_values_returns_zero`、`test_description_only_one_plan`、`test_two_different_questions_from_real_data` |
| 企业内变化只在共同样本检查 | `test_variation_checked_on_joint_sample`、`test_no_within_variation_keeps_only_descriptive` |
| 样本流失如实说明 | `test_joint_sample_loss_explained` |
| 字段说明修改后关联方案过期 | `test_store_versions_dependencies_and_no_auto_approval` |
| 原文件变化不能生成新方案 | `test_changed_source_blocks_generation` |
| 看过结果后保持探索属性及其原因 | `test_post_result_status_survives_revision_or_failed_recheck`、`test_exploratory_label_and_reason_visible_and_escaped` |
| 中文问答可选择不知道或取消 | `test_unknown_goal_and_field_are_preserved`、`test_guidance_cancel_does_not_save_answers` |
| 报告文本转义、标明静态快照 | `test_student_report_escapes_text_and_shows_scope` |

## 边界与下一步

本轮草案依赖研究者明确选列和核实说明，不能凭模糊方向自由提出新颖选题或确认文献贡献。企业内变化筛查只是原始变化检查，尚不检查双向固定效应吸收后的剩余变化。

尚需完成：更完整的方案编辑/选择交互、独立测量证据核查、描述统计与单一估计后端、推断诊断、计划与实际运行对照、效应量与区间解释、数值复现、真实学生理解度测试。报告是只读快照；网页填写和上传尚未实现。
