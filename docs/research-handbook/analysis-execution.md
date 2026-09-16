# 正式分析与独立数值复核

从工具仓库根加载接口，使用已定位的研究项目。用户通过自然语言确认研究方案，无需手工运行下列示例。

## 支持范围和环境

本文描述内置的独立数值复核路径：CSV、指定工作表的 XLSX、描述统计、企业/年度一项或两项固定效应的线性关联分析。标准误支持 classical、hc1、单维 cluster；完整案例、保留单例、95% 区间。默认 Python 正式估计，可显式选择 Stata；两者均用独立 Python 实现复核。其他方法、变量处理和 Agent 自动编程执行使用 [项目分析工作流](project-analysis.md)，不能把这里的内置范围当成 Agent 的方法能力上限。

准备工作仍只需 Python 3.9+ 标准库。正式分析建议用独立虚拟环境，安装固定的可选依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[analysis]'
```

验收版本：numpy 2.0.2、scipy 1.13.1、pandas 2.3.3、linearmodels 6.1、openpyxl 3.1.5、statsmodels 0.14.6。运行器检查版本，保存 Python、平台及相关依赖。不同环境须重新登记并核验。

**没有 Stata 也能完成正式回归、独立复核、报告与重跑。** Python 路径不探测、不导入或启动 Stata，也不要求 PyStata。Stata 路径另需用户自行安装并可运行的 Stata；首批仅实测 macOS arm64、Stata 19，Windows、Linux、其他版本未验收。环境按实际控制台返回记录版本、构建及版本类型，不根据应用文件名猜测。原生 `.dta`、任意已有 do-file 及第三方命令尚不接入。

## 输入和方案

```python
from econbiz.workspace import Workspace
from econbiz.analysis_input import import_table
w = Workspace.open(project_root)
w.import_file('raw-v1', source_path, role='raw_data', reason='登记实际研究材料')
table = import_table(w, 'table-v1', 'raw-v1', sheet='数据')
inventory = w.audit('inventory-v1', 'table-v1', entity='firm', time='year', numeric=['x', 'y', 'c'])
```

路径和字段均取自实际材料，CSV 省略 sheet。原始字节、文本前导零、缺失词保留。Excel 公式、错误值、日期/布尔、合并单元格及依靠显示格式补零的代码须先明确整理，不猜测。格式转换通过仍需盘点，盘点失败不能继续。

在完整研究方案中加入下列明确规则，用 register_plan/revise_plan 保存，然后记录适用授权。旧方案缺少 execution 时先形成可审阅修订，不从自然语言猜筛选条件：

```python
plan_content['execution'] = {
    'sample_filters': [{'field': 'year', 'op': 'ge', 'value': 2020}],
    'missing': 'complete_case', 'singleton': 'keep', 'confidence': 0.95,
}
```

空列表表示无额外筛选。每条仅含 field/op/value；eq/ne 使用文本，in 使用文本列表，ge/le 使用有限数值；多个条件按顺序共同满足，不执行表达式。记录各步剔除数、观测键、核心变量完整案例及控制变量额外损失，非法数值不能当作缺失删除。

fixed_effects 使用真实字段名，如 ['firm','year']；controls 不重复核心 x。standard_errors 必须有 method 和实际 rationale；cluster 另含 field，其他方法不带 field。描述统计使用 description/descriptive、空 controls/fixed_effects；mapping 列出数值字段，标准误设为 classical 并说明仅描述、不作回归推断。

项目特有处理脚本按已确认规则执行，保留代码和来源，对产出 CSV 重新登记、盘点并绑定方案。当前正式运行器使用固定入口，不提供任意脚本执行沙箱，也不自动核验所有自定义变量构造。

## 执行与报告

```python
from econbiz.execution import execute_analysis
from econbiz.result_report import write_result_report
run = execute_analysis(w, 'baseline-001', plan_id)
print(run['execution_status'], run['check_status'], w.last_receipt)
if run['execution_status'] == 'completed' and run['check_status'] == 'passed':
    report = write_result_report(w, 'baseline-report', 'baseline-001')
    print(report['files'], w.last_receipt)
else:
    print(run['content'].get('error'), run['content'].get('verification'))
```

plan_id 须是当前批准版本，既有授权适用时不重复确认。输入改变、过期、未批准或不支持的规则会被拒绝；计算失败及核验超差保存实际证据，不生成正式解释。

### 选择 Stata 或换引擎复现

用户明确要求 Stata 时，用同一接口显式选择；入口取自实际安装，不能照抄示例路径：

```python
run = execute_analysis(w, 'stata-001', plan_id, backend='stata',
                       stata_executable=actual_stata_executable)
# 同学没有 Stata：按同一当前方案和输入另建 Python 复现运行。
replica = execute_analysis(w, 'python-replica-001', plan_id,
                           backend='python', replication_of='stata-001')
```

省略 backend 时始终用 Python。Stata 入口可用参数、ECONBIZ_STATA_EXECUTABLE 或 PATH 上的 stata-mp/stata-se/stata 指定。启动检查失败就说明原因，不静默改用 Python。换引擎保持统计规则、输入及当前批准方案不变时无需重新批准，不自动标为探索；replication_of 必须指向同一方案版本和输入的有效运行。改变统计设定仍按原有研究修订规则处理。报告明确标注正式引擎及独立复核方法。

research/runs/运行标识/ 保存原输入、盘点、方案、参数、环境、manifest.json、冻结工具源码、生成的 run.py、样本链、结构化结果、独立参考与逐项偏差、状态和日志。工作进程核验后，接收方对实际读取的结果再次独立计算，最终核验保存为 parent-verification.json。running 和最终状态分别保存；kind=result 不代表通过核验。运行期间上游变化强制失败但仍保留证据；复核超时后已产生的结果继续计入结果暴露历史。

Stata 运行另冻结 execution.json、stata/ 下的 do-file、Mata 辅助代码、映射及传递数据；outputs/native/ 保存原生 e(b)、完整 e(V)、核心协方差、r(table)、实际输入回传、e(sample)、命令信息及 analysis.log。原生文件参与完整性校验，接收方重新解析后再与统一结果核对。环境记录可执行文件和官方命令实现的散列，不打包软件本体或授权文件。超时/取消会终止本次进程组，保留失败及部分输出；已产生的原生数值也计入结果暴露。

每次新 Stata 运行分配独立标识，原生元数据及完成标记须与冻结标识一致；同输入的旧输出也不能替代本次输出。冻结包重跑沿用原包身份，并写入新的输出目录。

报告包含 Markdown、HTML、CSV 系数表及判断—证据记录，保留全部系数和区间。原单位的条件关联不能自动写成因果效应、百分比或“没有影响”；控制变量没有单位时明确待核对。

## 重跑、过期与恢复

同一已确认方案可用新 run_id 自动重跑，不覆盖旧运行。冻结包目录中可执行：

```sh
python3 -B run.py --output replay-001
```

输出目录须为新标识，使用冻结源码和输入，检查版本及散列。这不改变研究状态；登记正式新运行用 execute_analysis。修改变量、盘点或方案后，依赖结果和报告过期；更新、确认并重跑。看到结果后修改方案须记录探索原因。报告文件是生成时快照，继续使用前用 project.require_usable 核对。中断后 Workspace.open 接续，再用新运行标识。

Stata 冻结包重跑要求匹配的 Stata 二进制和官方命令环境。没有 Stata 仍能读取、核对已保存的 Stata 运行和报告，或另建上述 Python 复现；后者是换引擎复现。旧版 Python 冻结包保持原格式和源码，不自动改写。

## 数值和诊断口径

Python 主估计用 linearmodels PanelOLS，Stata 用官方 areg 吸收一组固定效应，双向模型另一组使用显式虚拟变量；参考统一用独立 SciPy 稀疏投影、最小二乘与显式协方差。K 包含全部固定效应和解释变量；HC1 修正 n/(n−K)，单维聚类修正 G/(G−1)×(n−1)/(n−K)。聚类 p 值和区间用 t(G−1)，其他用 t(n−K)，可能与其他软件默认口径不同。Stata 核验同时比较核心解释变量的完整协方差，不以可能秩亏的协方差秩代替模型秩。

Stata 描述统计在 Mata 中计算，分位数沿用现有线性插值定义（type 7），不混用 Stata 默认分位数。中文、长字段名和文本企业代码通过安全别名映射；传递数据按列缩放并核对可逆性，不能保真时停止。原生数值保留，适配只负责结构、名称和单位还原，不用 Python 参考结果补值。

每次执行固定相对容差 1e−6、绝对容差 1e−8；样本键、模型和计数精确一致。完全吸收、共线、非有限值、非正自由度、零残差方差、不连通双向面板会停止估计；单例保留并报告。双向消元限 n×min(企业数,年度数) ≤ 1000 万单元，标准化条件数 ≤ 1e8；超过不自动换模型。参考投影须在预设迭代和正交性界限内收敛。

数值通过不认证变量构造、聚类层级合理性、小簇推断或因果识别。参考：[PanelOLS 选项](https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.model.PanelOLS.fit.html)、[聚类协方差](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_cluster.html)。具体实施以运行包记录的本地版本为准。
