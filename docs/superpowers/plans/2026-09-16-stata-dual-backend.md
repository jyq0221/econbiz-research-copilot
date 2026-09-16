# Stata 可选执行引擎实施计划

> **For agentic workers:** 使用 subagent-driven-development 执行独立实现子任务，并分别进行规格与质量审阅。用户已授权开始实施；任务之间连续推进，不重复请求授权。

**Goal:** 增加真实 Stata 回归及 Python 独立复核，保留无 Stata 环境下完整的 Python 使用路径。

**Architecture:** 公共执行接口默认 Python，显式选择 Stata 时才探测并启动其批处理进程。两条路径共用冻结方案、运行状态、独立参考、报告和恢复；Stata 的 do-file、输入、实际样本、原生矩阵和日志与结果一并保存。历史 Python 格式继续兼容。

**Tech Stack:** 现有 Python 3.9.6 与 analysis 固定依赖；首批实测 macOS arm64 + 本机 Stata 19 控制台（实际探针报告 IC/Unix，不推断 MP）。Stata 不成为 Python 路径的安装或运行依赖。

设计依据：[双引擎设计](../specs/2026-09-16-stata-dual-backend-design.md)。维护位置按项目要求保持 codex/framework-foundation；本轮实现不自动更新 main 或推送。

## 文件职责

- `econbiz/processes.py`：受控子进程与整个进程组的超时/取消收尾。
- `econbiz/stata_runtime.py`：按需发现、启动探针、版本与可执行文件身份。
- `econbiz/stata_engine.py`、`econbiz/stata_script.py`：生成冻结 Stata 文件、运行、提取并验证原生结果。
- `econbiz/numerical_check.py`：保留旧 Python 契约，增加显式 Stata 契约及核心协方差比较。
- `econbiz/execution.py`、`econbiz/run_worker.py`：选择引擎、冻结配置、原生证据登记、接收方复核与复现关联。
- `econbiz/result_report.py`：显示正式引擎与复核方法。
- 对应 `tests/test_processes.py`、`test_stata_runtime.py`、`test_stata_engine.py`、`test_dual_backend.py`：临时合成数据与实际进程验证。

## Task 1：环境与进程生命周期

- [x] 编写失败测试：无效入口、实际启动探针、超时后子进程不继续写文件、正常完成、取消。
- [x] 运行测试确认缺少接口的失败。
- [x] 实现进程组收尾；Stata 默认只接受已验证的 macOS/19 环境并提供明确错误。
- [x] 用临时 do-file 实测 Stata，记录版本、构建、可执行文件校验值，避免收集授权文件。
- [x] 复测并审阅。

## Task 2：Stata 数值执行与原生证据

- [x] 先写真实 Stata 测试：平衡/非平衡 × 三种固定效应 × 三种标准误，与现有 LSDV 参考比较。
- [x] 冻结受控字段名、数值传递文件、映射和 do-file；保留实际输入回传及 e(sample)。
- [x] 实现 areg + 另一组虚拟变量；保存 e(b)、e(V)、r(table)、原始模型/自由度信息与高精度输出。
- [x] 在 Stata/Mata 计算描述统计及现有线性插值分位数；数值缩放明确可逆，不调用 Python 主回归或参考来填值。
- [x] 覆盖单例、奇异模型、字段映射、数值尺度、输出缺失及篡改；独立规格、质量审阅。

接口约定：`build_bundle(rows, spec, *, run_token)` 返回文件名到字节；`run_estimation(rows, spec, bundle_dir, output_dir, runtime, timeout=...)` 执行并返回统一结果；`read_result(rows, spec, native_dir, *, run_token)` 供接收方从原生文件重新解析。Stata 结果额外保存核心解释变量协方差矩阵，Python 旧格式不变。运行模块只按需导入。

## Task 3：双引擎工作流与复核

- [x] 失败测试覆盖默认 Python、拒绝未知引擎、Python 路径禁止 Stata 导入/探测、Stata 完整运行和重跑。
- [x] `execute_analysis(..., backend='python', stata_executable=None, replication_of=None)`；选择及复现来源冻结在配置中。
- [x] Stata 完整原生文件加入版本与散列记录，原始结果缺失/旧完成标记/伪造引擎不能通过。
- [x] 复核期望引擎来自冻结配置，保留独立重算；不以 Stata e(rank) 代替设计秩。
- [x] 超时/中断/上游变更均保留失败及已产生结果暴露记录；原有 Python 故障测试继续通过。
- [x] 报告显示正式引擎，纯 Python 环境仍能读取已有 Stata 结果；历史冻结包不改写。

## Task 4：入口与文档

- [x] 更新维护源 Skills、正式分析手册及 README，明确 Python 默认、Stata 可选、同等检查标准和实际平台范围。
- [x] 同步两套 Skills 副本；更新设计实施状态和版本号。
- [x] 将本轮支持范围与真实证据写入 `docs/stata-validation.md`。

## Task 5：最终验收

- [x] 全套测试、无 site-packages 的阶段 A、Skills 一致性、差异检查。
- [x] 在禁用 Stata 导入/发现/启动的条件下，实际 Python 回归、报告、恢复、冻结重跑通过。
- [x] 真实 Stata 临时项目从 CSV/XLSX 到回归、独立复核、报告、恢复、换引擎复现通过。
- [x] 验证旧 0.2.0a1 冻结包仍可独立重跑。
- [x] 检查导出使用版的文件、安装和运行，浏览器检查新报告。
- [x] 最终规格与代码质量审阅，修复发现；提交开发成果并报告验证结果与限制。

## 收尾记录

全部五项完成。最终 193 项测试通过，包含真实 Stata；标准库环境 122 项通过、71 项按条件跳过。最终使用包的 ZIP、独立 clone 和安装版本均在禁止 Stata 访问时完成 Python 回归、报告、恢复和冻结重跑。旧 0.2.0a1 包可读且独立重跑通过，XLSX/Stata/Python 接续与报告浏览器显示完成。

环境/进程、原生数值、工作流分别经规格和质量审阅，整体复审通过。修复项包括身份摘要遗漏、缩放下溢、日志/路径证据、不可读输出收尾、结果暴露，以及同输入旧输出的运行标识绑定。每次新 Stata 运行用独立标识，冻结包重跑保留原包身份。细节与本地验收证据见 [双引擎验收](../../stata-validation.md)。本轮保留在开发分支，不更新远端 main 或发布。
