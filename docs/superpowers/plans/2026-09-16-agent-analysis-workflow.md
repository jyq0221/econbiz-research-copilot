# Agent 分析工作流实施计划

> **For agentic workers:** Use subagent-driven-development for bounded implementation and review. User has approved the workflow and reduced repeated confirmations. Continue on the existing development branch; do not publish main.

**Goal:** 让宿主 Agent 能判断研究方法，生成并实际执行项目脚本，复用常见数据处理，并准确交付执行与复核状态。

**Architecture:** 研究判断由现有 Skills 驱动；确定性 Python 接口负责处理规则、运行材料和状态。现有正式结果接口保持原门槛，通用脚本使用独立的 script_run 记录，不能通过自报 passed 冒充独立核验。

**Tech Stack:** Python 3.9+ 标准库、现有固定分析依赖、可选 Stata 19；unittest；临时合成项目。

## Task 1 — 有顺序的数据处理及代码生成

文件：新增 `econbiz/preprocessing.py`、`econbiz/preprocessing_script.py`、`tests/test_preprocessing.py`。

- [x] 先编写并运行失败测试：原值保存、分组缩尾线性分位数、对数定义域、零分母、缺失传播、间隔滞后、重复键、合并扩行。
- [x] 实现 `prepare_data(raw: bytes, recipe: dict) -> (bytes, dict)`。recipe 包含 schema_version=1、keys 和 steps；每步须显式 op/source/target 及所需规则。标准库执行缩尾、ln、log1p、ratio、interaction、indicator、center、standardize、lag、difference、filter；输入列不能覆盖；无序或不明确规则拒绝。
- [x] 实现 `merge_data(left, right, *, keys, relationship, how)`：支持 one_to_one / many_to_one，明确键关系和字段冲突、缺失键、未匹配计数，拒绝扩行或静默去重。
- [x] 实现 `render_preparation_script(recipe, *, backend, input_name='input.csv', output_name='processed.csv')`。Python 使用随运行包冻结的实现；Stata 使用原生命令及相同分位数定义，不依赖用户 ado。脚本保留实际阈值与处理记录。
- [x] 核对手工可计算样例及真实 Python 脚本；可用时真实 Stata 逐行比较；数值失败不能靠放宽容差解决。

## Task 2 — 通用项目脚本的登记、冻结与执行

文件：新增 `econbiz/project_scripts.py`、`econbiz/script_worker.py`、`tests/test_project_scripts.py`；修改 `econbiz/plans.py`、`econbiz/state.py`、`econbiz/research_history.py`。

- [x] 先测试任意方法不能借固定执行入口冒充通过；显式 `execution_route='project_script'` 的完整研究方案可沿用授权登记，不再因 model 名称不在内置集合而拒绝。
- [x] `save_project_script(workspace, script_id, plan_id, *, files, entrypoint, backend='python', inputs, expected_outputs, reason)` 保存项目代码；inputs 映射运行相对文件名到已登记来源/盘点 ID；方案冻结当前版本；script 内容标记检查仅为文件与绑定，非统计认证。
- [x] `execute_project_script(workspace, run_id, script_id, *, timeout=300, stata_executable=None, retry_of=None)` 冻结所有源码、输入、方案、环境、工具；执行独立受控进程，Python 路径不触发 Stata 探测。显式 Stata 通过 wrapper do-file 及完成标记判断是否实际完成。
- [x] 每次新目录、新标识；运行中改变材料、缺失输出、超时或错误均保存日志及部分输出。未独立统计核验的运行保持 completed/pending；自写 verification.json 不改变状态。原 finish_result 不放宽，新增专用 finish_script_run。
- [x] 对执行中输出/失败日志保守记录结果暴露；后续研究变更要求探索理由。技术重跑可引用同一方案版本失败尝试，不要求重复批准。
- [x] `write_script_report(workspace, run_id)` 读取实际状态与已冻结材料，给出可读执行说明和证据链接；不能调用已核验正式结果报告。
- [x] 冻结包支持 `run.py --output replay-ID` 在新目录重跑，核对文件哈希与运行环境；禁止覆盖原输出和使用旧完成标记。

## Task 3 — Agent 指引、使用手册与场景验收

文件：`.agents/skills/econbiz-{research,design,analysis,interpret}/SKILL.md` 及同步副本；`AGENTS.md`、`README.md`、`docs/research-handbook/project-analysis.md`；新增 `tests/test_agent_analysis_workflow.py`。

- [x] 指引明确根据研究问题、字段含义、实际数据和识别依据给出推荐；模型、DID/IV、权重、聚类分别判断。不要求学生先选择模型或写脚本。build_candidates 只是有界辅助，不能代替 Agent 研究判断。
- [x] 简短方案后沿用授权自动处理、编程、运行、技术修错和交付；实质研究选择超出授权才提问。
- [x] 增加完整手册及真实字段示例：处理规则 → 文件生成 → 脚本保存运行 → 处理后数据登记 → 已有固定效应正式运行和报告。另用 OLS 自定义脚本验收未内置模型，不声称普适核验。
- [x] 手工宿主验收：读取合成数据和已授权要求，生成真实 Python 项目；制造技术错误、修复重跑、保留旧证据；无 Stata 完整执行。真实 Stata 另行验证 do-file 和处理数值。
- [x] 独立规格审查、代码质量审查；修复问题后复查。
- [x] 运行 `python3 scripts/sync_skills.py --check`、`python3 -m unittest discover -s tests`、`python3 -S -m unittest discover -s tests`、`git diff --check`。版本声明只写已经验收的能力。

## 范围与验收说明

本计划实现设计第一批。DID/IV/权重/多维聚类可由 Agent 论证并生成项目脚本，但这些方法的通用独立核验器属于后续逐项扩展，不能写成已实现。程序成功退出只是执行检查；处理数值比对与统计结果复核分别报告。所有开发测试用临时合成项目，不创建个人研究。

## 完成记录

第一批实现和宿主验收完成。239项全套测试通过（含真实Stata），标准库环境149项通过、90项按范围跳过；Skills同步及差异检查通过。详见 [验收记录](../../agent-analysis-validation.md)。本地开发分支保存，尚未推送或更新main。
