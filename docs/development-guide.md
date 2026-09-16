# 开发与工具说明

主入口是宿主 Agent 中的自然语言研究请求。AGENTS.md 负责维护/研究分流，五个 Skills 以 .agents/skills 为源，.claude/skills 为普通文件副本；用户无需全局安装或运行同步脚本。

## 环境和验证

研究准备使用 Python 3.9+ 标准库；阶段 B 正式分析需要 pyproject.toml 的固定 analysis 可选依赖，未安装时仍可使用阶段 A。statsmodels==0.14.6 是 linearmodels 的依赖，测试也用其显式虚拟变量 OLS 作为第三方参考；Python 主回归调用 PanelOLS，可选 Stata 主回归调用 areg，独立参考不调用这些估计器。可选研究 Git 需要本机 Git。维护仓库不放真实研究数据，自动化测试在临时目录建立合成项目。

```sh
python3 -m unittest discover -s tests -v
python3 scripts/sync_skills.py --check
git diff --check
```

真实 Stata 测试使用 `ECONBIZ_TEST_STATA=实际可执行路径 python3 -W error -m unittest discover -s tests -q`；未设置时明确跳过，不能据此声称 Stata 实测通过。开发版本验收见 [双引擎验收](stata-validation.md)。

修改维护源后运行 `python3 scripts/sync_skills.py`，提交两套普通文件。同步只处理五个明确的 econbiz Skill，检查模式不写文件；其他技能不动。程序测试不代表模型实际读取了 Skill，见 [测试情境](../tests/agent_cases/README.md) 和 [验证记录](agent-entry-validation.md)。

## 公共接口

实际研究的公共调用约定见 [工具契约](research-handbook/tool-contracts.md)。八组完整合成示例见 [开发验收示例](developer/tool-contract-examples.md)，由测试在临时项目实跑。

| 模块 | 职责 |
| --- | --- |
| state / files | 权威状态、版本、依赖、内容校验及不可覆盖文件 |
| workspace / checkpoints | 三类目录、导入、保存回执、检查点和追加恢复 |
| records / progress | 六种科研记录、任务、概览与跨会话恢复 |
| plans / research_history | 数据与证据绑定、版本确认、共同结果后探索规则 |
| audit / candidates / reports | CSV 结构检查、固定规则教学草案和 HTML 报告 |
| analysis_input / execution_spec | XLSX/CSV 接入、明确执行规则及逐步样本审计 |
| estimation / numerical_check | PanelOLS 主估计与独立 SciPy 稀疏投影/数值复核 |
| analysis_environment / execution / run_worker | 固定依赖、冻结代码/输入/环境、子进程执行与失败收尾 |
| stata_runtime / processes | 按需探测 Stata、冻结身份与进程组超时/取消收尾 |
| stata_engine / stata_script | 原生估计、传递保真、样本及矩阵证据解析 |
| result_report | 只消费已核验结果的表格、判断—证据及中文解释 |
| research_git | 明确范围内的单项研究本地 Git，可选且无远端操作 |

旧 schema_version=1 项目可读，原 reports/ 布局不自动搬迁。新项目使用 research/reports/，来源采用相对引用；历史 input_path 绝对路径保持兼容。
阶段 B 公共接口见 [正式分析](research-handbook/analysis-execution.md)。状态 finish_result 收尾尚未完成的 running/stale result，沿冻结依赖保存成功或失败证据；上游运行期间变化强制失败，日志仍登记。
任务和讨论摘要的 outputs 使用版本引用，不硬连成反向依赖环。消费时实际核验文件和版本，不能仅看 completed/passed。

## 内部命令兼容

保留 `python3 -m econbiz` 下的 init/audit/status/plan/approve/guide，供维护、测试和协助试用使用。

```sh
python3 -m econbiz --help
python3 -m econbiz init /tmp/econbiz-synthetic-study --direction '合成数据演示'
python3 -m econbiz audit /tmp/econbiz-synthetic-study examples/panel.csv --entity firm --time year --numeric x y
```

每次盘点返回实际 inventory 标识，guide/plan 使用该标识；init 拒绝已存在目录。guide --brief examples/research-brief.json 是内部固定规则草案，不替代研究论证。
不把示例确认写入真实研究。原 CLI 自由文本凭据保留为调用者声明；Agent 应保存 user_decision 并使用返回的真实路径。

## 版本和发布

材料先写文件、再写状态、最后更新概览。状态失败保留旧状态与孤立文件；概览失败在回执单列。仅支持一个写入者，不承诺并发合并或自动云端备份。
可选研究 Git 只处理所选代码/文本/元数据，单文件上限 1 MiB；已有暂存、无身份、越界、隐藏凭据或原始数据范围会拒绝。它不设置远端、不推送、不改全局身份，本地文件历史仍可继续使用。
本地源码提交和研究文件保存是不同记录。对外发布须有明确请求；宿主兼容及初学者试用结论需实际证据。

## 默认使用版本与开发分支

`main` 为使用版本，默认 clone 和 ZIP 都保留两套项目 Skills、模板、econbiz、入口、软件包配置、四份运行手册及试用反馈模板。main 使用文件树不包含 examples、tests、scripts、开发文档或实施记录。既有 Git 历史不重写。

完整维护材料保存在 `codex/framework-foundation` 分支。开发时明确选择该分支：

```sh
git clone --branch codex/framework-foundation --single-branch https://github.com/jyq0221/econbiz-research-copilot.git
```

开发分支的 `.gitattributes` 通过 `export-ignore` 导出使用文件。发布时，在临时隔离的 main checkout 中用开发分支的 `git archive` 内容替换受版本控制的文件，再正常提交、推送；不得把开发分支整体合并到 main，也不得强制推送或重写历史。检查删除项都是已保留在开发分支的维护材料，入口、两个 Skill 包、工具代码与四份手册必须完整保留。

`tests/test_distribution.py` 在临时仓库生成真实 ZIP，检查排除范围、保留入口、相对链接，以及解压后独立保存/接续；还将同一使用文件树建立为 main 并实际 clone，比较文件字节且独立运行。发布后从 GitHub 默认 clone、实际下载 ZIP，逐文件核对一致性与可运行性。

测试数据独立作为 `trial-data-v1` Release 附件发布，下载地址写在 README。附件包含完整合成面板、带问题的练习版、字段说明与核对答案；数据不提交到 main。发布后重新下载附件，核对散列、行数、企业年度键和预设问题。

归档属性依据 [Git archive 文档](https://git-scm.com/docs/git-archive)。旧提交的 ZIP 内容不会被新规则追溯修改；请从当前默认分支重新下载。
