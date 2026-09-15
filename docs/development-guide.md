# 开发与试运行说明

本文面向开发者，以及协助同学试用的技术人员。项目定位和当前可用范围请先阅读 [项目介绍](../README.md)。

当前基础框架使用 Python 3.9+ 标准库，无运行时第三方依赖。下列命令均在仓库根目录运行。已接入固定规则的引导式草案与静态 HTML 报告；尚未接入自由选题生成、统计估计、判断—证据表或网页操作界面。

实现依据为用户已确认采用的 [设计与制作标准 v1.1](design-and-development-standard.md)。标准描述预期能力，实际覆盖情况以 [阶段验收记录](foundation-validation.md) 为准。

## 试运行

在仓库目录执行以下命令。样例全部为合成数据，输出写入被 Git 忽略的 `research-projects/`。

```sh
python3 -m econbiz init research-projects/demo --direction "了解合成指标 x 与 y 的关联"
python3 -m econbiz audit research-projects/demo examples/panel.csv --entity firm --time year --numeric x y
python3 -m econbiz status research-projects/demo
```

`audit` 输出一个 `inventory-…` 标识。用该实际标识登记教学方案：

```sh
python3 -m econbiz plan research-projects/demo examples/candidate-plan.json --id candidate-1 --inventory <实际inventory标识>
```

方案登记后停留在“需要决策”。研究者核对目标、字段含义、缺失规则、样本及方法条件后，可以显式保存决定：

```sh
python3 -m econbiz approve research-projects/demo candidate-1 --actor "确认者姓名" --reason "核对内容及选择理由" --evidence "实际决策记录位置"
```

确认绑定当前方案版本，既不执行估计，也不认证方法假设。确认者和证据位置由调用者提供；此本地框架没有身份认证，也不自动验证外部证据内容。不要把示例占位文本当作真实决定。

若项目目录已存在，初始化会拒绝覆盖。检查失败时仍保存报告，并返回退出码 2。成功退出码为 0。

## 文件与核心接口

| 位置 | 职责 |
| --- | --- |
| `econbiz/state.py` | 项目状态、历史版本、依赖、确认、原子保存与恢复 |
| `econbiz/audit.py` | 唯一键、原始缺失标记、数值合法性和文件校验值 |
| `econbiz/plans.py` | 候选方案字段契约、方法边界和确认检查 |
| `econbiz/cli.py` | 本地命令入口 |
| `econbiz/candidates.py` | 已核实字段到草案、实际样本事实、探索记录与依赖 |
| `econbiz/guidance.py` | 中文问答和未知信息处理 |
| `econbiz/reports.py` | 转义后的本地静态 HTML 对照报告 |
| `tests/` | 错误注入及真实命令行流程测试 |
| `examples/` | 合成数据与教学方案 |

每个研究项目保存 `research_state.json` 和 `reports/`。计划修改使用 `Project.revise(id, content, reason)`，它保存旧版，清除当前版可用状态，并递归标记下游过期。重新生成下游时仍需显式修订和检查。中断后 `Project.load()` 将未结束的运行转为失败；后续 `save()` 持久保存恢复记录。状态命令只读展示，不写入恢复记录。

`register_plan()` 接收真实字段绑定方案；`require_approved_plan()` 是未来估计器必须使用的入口关口。通用产物接口是供受信任程序使用的底层 API，不是防篡改安全边界。当前状态文件为单进程、单写入者设计，不支持并发编辑。

CSV 盘点只解释明确列出的缺失标记，保留原始字符串，不清洗或填零。主体与期间键按原字符串比较，年度格式和经济口径仍需核实。原文件在盘点后变化或丢失时，消费关口会阻断旧盘点与下游使用。

## 验证与下一步

```sh
python3 -m unittest discover -s tests -v
git diff --check
```

阶段设计见 [框架实现说明](framework-foundation.md)，测试证据和剩余要求见 [阶段验收记录](foundation-validation.md)。

下一阶段完善草案审阅与修改，再实现单一 Python 描述统计/固定效应估计后端及独立数值核对，最终完成结果证据对照与口径修改后的重跑闭环。

## 引导式方案准备

完成 `audit` 后，用实际 inventory 标识启动中文问答。旧版本盘点若没有 `key` 信息，需重新执行 `audit`，原盘点记录仍然保留。

```sh
python3 -m econbiz guide research-projects/demo --inventory <实际inventory标识>
```

问答询问研究目标、关注现象、可选解释因素，以及字段定义、单位、时间、来源、缺失含义与测量距离。选择 0 或留空保留未知；Ctrl+C 取消不保存本轮回答。程序不推测字段经济含义。

协助者已有整理后的字段说明时可跳过问答：

```sh
python3 -m econbiz guide research-projects/demo --inventory <实际inventory标识> --brief examples/research-brief.json
```

输出在项目 `reports/`，包含静态 HTML。零方案是正常研究状态，命令仍返回 0 并保存待核实事项；非法字段、数据版本变化等技术错误返回 2。所有候选方案仍需确认；关联草案的 `standard_errors.method` 为 `needs_decision`，不能直接批准用于执行。

核心 API `store_candidates(project, inventory_id, brief, prefix)` 返回 `(updated_project, comparison)`，不修改传入的 Project。成功后由调用者保存返回的新项目；内部先在副本中组装 intake → comparison → plan，失败不会污染原对象。输出 HTML 与状态文件不是跨文件事务，若文件保存中断，可留下没有被状态引用的报告，不能以报告存在推断方案已保存。

新输入修改使用 `Project.revise()` 后，原对照与方案过期；可再以新 prefix 生成方案包，旧包保留。原始输入路径或校验值变化会被消费关口拒绝。每个方案包保留自己的输入版本，HTML 是生成时的静态快照，不自动更新。

已有结果（包括曾完成后修订、复查失败或已过期的结果）时，新草案需要 `exploration_reason`，并在报告上标明“结果之后的探索”。对旧格式中无法判明是否曾执行的过期结果，按已有结果材料保守处理。当前仅追踪项目内记录，不能获知未登记的外部运行。

见 [阶段设计](candidate-guidance.md) 与 [阶段验收](candidate-guidance-validation.md)。
