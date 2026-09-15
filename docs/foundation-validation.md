# 基础框架阶段验收

日期：2026-09-15。基准：设计与制作标准 v1.1。范围：框架第一阶段，不是完整 V0.1 验收。

## 已执行验证

- 环境：本机 Python 3.9.6，标准库，无运行时第三方依赖。
- 自动测试：`python3 -m unittest discover -s tests -v`，32 项通过。
- 空白与补丁检查：`git diff --check` 通过。
- 实际命令行：临时目录中完成初始化、审计 9 行/3 个主体的合成 CSV、登记教学方案、查看状态。方案停在 needs_decision，决策记录为空，没有代替研究者确认。
- 自动测试另行在临时目录验证了显式确认命令和失败审计的非零退出码；全部身份/证据值仅为测试夹具，不代表真实研究决定。
- 独立审查发现的过期状态绕过、历史记录损坏漏检、解析失败记录缺失、多行 CSV 定位偏移均已加入回归测试并修复。

## 要求与证据对应

| 标准要求 | 本阶段证据 | 边界 |
| --- | --- | --- |
| 保留缺失含义，不未经确认填零 | `test_inventory_preserves_missing_states`、`test_unknown_text_not_silently_converted` | 只盘点，不执行缺失处理 |
| 数据唯一键与异常值检查 | `test_duplicate_keys_are_errors_with_source_lines`、`test_blank_keys_and_nonfinite_values_block` | 尚未实现合并、样本链和回归数值检查 |
| 错误留下证据 | `test_malformed_csv_failure_persisted`、`test_failed_audit_persisted_with_nonzero_exit` | 输入不可读取时返回明确文件错误；没有虚构输入哈希 |
| 候选方案绑定实际字段 | `test_nonexistent_fields_rejected`、`test_incomplete_plan_rejected` | 接收人工/上游输入，不自动提出问题或比较方案价值 |
| 首版不支持方法必须阻断 | `test_unsupported_design_preserved_but_blocked` | 保存原目标与方法，不改写成关联；尚无估计器 |
| 确认绑定特定方案版本 | `test_approval_gate_and_version_binding` | 本地决策记录，不是身份认证或假设认证 |
| 修改口径使下游过期 | `test_recursive_invalidation_keeps_history`、`test_stale_inventory_invalidates_approval` | 支持核心 API 显式修订，尚无修订向导 |
| 不能绕过过期状态复用结果 | `test_stale_state_cannot_be_reset_without_revision` | 必须修订后重新检查 |
| 输入版本一致 | `test_changed_source_cannot_reuse_inventory` | 消费前重新校验源文件字节；尚无原始数据快照归档 |
| 中断恢复不误用未完成产物 | `test_resume_marks_interrupted_work_failed` | 本地单写入者；状态查询只读，恢复事件在后续 save 时落盘 |
| 历史证据与文件有效性 | `test_roundtrip_and_corrupt_state`、`test_incomplete_historical_record_rejected` | 原子写单个文件；不是数据库事务或防篡改存储 |

## 尚需完成的验收

以下标准要求尚无实现或验证证据，不能标记完成：方向与字段说明生成候选方案；合并关系检查；控制变量导致的样本变化；固定效应吸收与剩余变化；估计和推断诊断；计划与实际运行参数对照；独立数值参考及容差复现；结果效应量与区间解释；判断—证据表；结果后的探索标记自动约束；文献位置核查；真实新手理解度测试。

下一阶段应先补全方向入口和方案比较，再接入单一估计后端，沿同一状态/证据链实现第一次完整闭环。
