# 研究文件和记录

每项研究使用独立目录，包含 `literature/`、`data/`、`research/`。子目录按需创建。
`research_state.json` 保存产物、版本、依赖与决定，`研究进展.md` 是可重建视图。
从工具仓库根加载入口；研究路径作为 Workspace 的显式参数。同一研究同时只由一个 Agent 写入。

## 保存与继续

用 `Workspace.create` 开始实际研究，用 `Workspace.open` 继续；普通概念咨询不创建项目。
来源由 `import_file` 登记：复制时保留真实字节；外部索引只记录用户提供的绝对路径，恢复仍依赖外部原文件。
新版本保存在材料标识的 `v0001/`、`v0002/` 等目录，旧文件不覆盖。
保存顺序为校验副本、写版本文件、原子保存状态、更新概览。
状态保存失败时旧状态有效，已写出的孤立文件等待核实；同内容可重试，不自动承认其已登记。
概览保存失败不会回滚状态，检查返回的 `state_saved`、`view_saved` 和 `view_error`。

## 六种研究记录

| kind | 内容与来源 | 保存位置 |
| --- | --- | --- |
| research_context | 研究问题、已知/未知、约束与下一步；未知保持空列表或注明待核实 | research/sessions |
| literature_evidence | 实际 source、阅读范围、原文定位、判断、支持和限制 | literature/notes |
| concept_plan | 无数据也可保存的问题、目标、理由和数据缺口 | research/plans |
| session_note | 本轮摘要、带来源的事实、决定、实际产物、问题、下一步和授权范围 | research/sessions |
| user_decision | 当前方案具体版本、可见确认摘录、适用范围和实际记录时间 | research/decisions |
| research_task | 业务状态、输入版本、实际输出、下一步和等待原因 | research/tasks |

可读 Markdown 和结构化 JSON 同时保存。格式检查通过只说明记录可读。
文献阅读范围使用 metadata/abstract/excerpt/full_text；metadata 的 claim/support 留空，不能填写经验发现。
事实区分 user_quote/source_excerpt/program_output/agent_proposal；用户说明标记 reported 或 needs_check，Agent 建议标记 proposed。
材料摘录和计算记录附 `source_ref={artifact_id, version}`；用户可见摘录可用 `local:记录标识`，不编造平台消息 ID。
程序不能认证摘录来自某人、全文是否真正读完、假设是否有效；Agent 必须对照实际材料。

确认摘录本身不批准方案。只有当前可见授权明确适用于具体版本时才调用 `Project.approve`，确认证据使用保存函数返回的路径。
任务输出采用 `{artifact_id, version}`，已完成任务必须存在可用产物。输入变化或输出版本变化后，概览显示需要重新核对。

## 更正、检查点与恢复

更正使用相同记录标识并说明原因，旧版本继续可读，下游记录会过期。
概览中的手动修改会另存 `research/history/view-edits/`，作为待核实输入，不自动覆盖状态或批准分析。
检查点保存状态和文件清单，不重复复制原始数据；`complete=false` 表示有缺失、改变或仅外部保存的材料。
对比会重新核对真实文件。恢复新增修订，保留后来历史；旧依赖不匹配时先重选输入，恢复方案需重新确认。
移走整个研究目录后项目内引用仍然有效；外部来源可用 `relocate_source` 核验相同内容再登记新位置。

具体可运行示例见 [工具契约](tool-contracts.md)。可选 Git 的启用范围和限制在相关功能验收后补记。
