# 从研究问题到可运行项目脚本

用户交代研究问题和材料，Agent 负责读数据、判断方法、处理变量、编写代码、运行、修错和交付。先给简短的“模型＋处理方案”，已有授权内连续推进。只对超出授权的变量含义、样本或识别策略改变请求决定。

## 1. 先判断，再编程

核实观察单位、字段说明、结果变量性质、缺失与极值、键、年份及可用变化。方法要服务于研究问题：区分描述、关联、因果和预测，分别解释模型、比较策略、权重和标准误。DID 要检查处理时间与比较对象，IV 要有工具变量的研究依据；不能仅凭数据分布、相关系数或显著性确定识别策略。

通常给一个推荐方案与必要替代方案。模型是否内置不决定研究问题是否可做。内置 `build_candidates` 是有界讨论辅助；Agent 仍须结合文献与实际数据完成判断。先明确方法与诊断，再选择已有固定执行器或项目脚本路径。

缩尾、对数和删样本不是通用默认设置。按研究口径确定变量、分组、阈值、顺序、缺失和异常处理；已获明确授权就不用再次询问。技术错误自动修复；不能通过修错偷偷删观测、改成 ln(1+x)、换模型或改变聚类层级。

## 2. 可复用的有序处理规则

`econbiz.preprocessing.prepare_data(raw_bytes, recipe)` 返回处理后的 CSV 字节与实际处理记录。原始列和值保留；新增列不能覆盖既有列。`keys` 必须是非空、无缺失且唯一的行标识。数字中的空字符串视为缺失；其他缺失词先按其实际含义明确整理，不静默转为零或丢弃。

例如实际数据以 firm/year 为键，对 leverage 按年缩尾，再对正值 assets 取 ln：

```python
recipe = {
    'schema_version': 1, 'keys': ['firm', 'year'],
    'steps': [
        {'op': 'winsor', 'source': 'leverage', 'target': 'leverage_w',
         'lower': 0.01, 'upper': 0.99, 'by': ['year']},
        {'op': 'ln', 'source': 'assets', 'target': 'ln_assets', 'invalid': 'error'},
    ],
}
```

参数由 Agent 根据已确认口径生成，不要求研究者填写。

| op | 明确参数（除 op） |
| --- | --- |
| winsor | source、target、lower、upper、by；使用当前步骤样本的线性插值分位数（type 7），记录各组阈值和受影响数 |
| ln / log1p | source、target、invalid（error / missing）；两种变换不可互换 |
| ratio | numerator、denominator、target、zero（error / missing） |
| interaction | sources、target；缺失传播 |
| indicator | source、target、value、missing（error / missing / zero） |
| center | source、target、by |
| standardize | source、target、by、ddof（0 / 1）、zero（error / missing） |
| lag / difference | source、target、entity（字段列表）、time、interval（正整数）；按真实时间间隔查找，断年留缺失 |
| filter | source、operator、value（具体可用操作见接口）；有顺序的筛选，不修改原列 |

`merge_data(left_bytes, right_bytes, keys=[...], relationship='one_to_one' 或 'many_to_one', how='left' 或 'inner')` 检查键与合并关系、重名字段和未匹配数量，不静默去重或多对多扩行。当前复用工具不含任意重塑、聚合、插补及训练/测试分割；这些按具体方案编写项目代码并核对。预测任务的缩尾、标准化参数须由训练样本拟合，不能直接对含测试集的数据使用整体处理规则。

`econbiz.preprocessing_script.render_preparation_script` 生成 Python 或原生 Stata/Mata 代码。Stata 处理脚本目前要求被引用字段为 ASCII 字母开头、最长 32 字符；不支持的名称须先明确映射，不能默默改列。原生数值输出要能往返还原。由于两种语言可能以不同末位文本表示同一个浮点数，Stata 不接受把先前派生的数值列当作文本类别、分组或实体键；0/1 indicator 例外，数值筛选可正常使用。Python 路径不需要 Stata。

## 3. 保存和运行项目代码

正式研究方案仍用 `register_plan/revise_plan` 绑定实际 inventory、测量、样本、标准误与研究理由。在方案加入 `execution_route='project_script'` 可批准内置集合之外的具体方法。批准证明用户同意该方案，不证明软件执行或数值正确；现有授权适用时记录真实摘录即可。

以下完整方案对象展示接口字段，采用本手册的贷款获批字段。Agent 应按实际读到的定义、资料版本和研究判断生成内容；不能照抄示例作为研究者已确认的事实。处理后真实字段通过重新盘点后才可进入 mapping/controls。

```python
plan_content = {
    'question': '杠杆与贷款获批概率存在怎样的条件关联？',
    'goal': 'association', 'judgment': '估计方向和精度，不预设显著性',
    'competing_explanations': '规模、行业和期间差异可能同时关联杠杆与获批',
    'mapping': {
        'y': {'field': 'approved', 'definition': '1 获批，0 未获批', 'unit': '0/1',
              'time': '公司年度', 'source': '随数据提供的字段说明', 'version': '1'},
        'x': {'field': 'leverage', 'definition': '负债与资产比值', 'unit': '比例',
              'time': '公司年度', 'source': '随数据提供的字段说明', 'version': '1'},
    },
    'sample': '按已经确认的完整案例规则保留企业年度观测，并报告损失',
    'comparison': '在规模、行业和年度条件下比较不同杠杆的获批概率',
    'missing_rule': '逐项报告缺失后完整案例；不填零',
    'model': 'logit', 'controls': ['assets'], 'fixed_effects': ['year', 'industry'],
    'standard_errors': {'method': 'cluster', 'field': 'firm',
                        'rationale': '允许同企业跨年误差相关'},
    'conditions': '核对0/1编码、样本变化、分离、模型收敛及可用企业簇数',
    'feasibility': '依据实际数据与环境检查后记录', 'data_gaps': [],
    'priority_reason': '结果变量为二元获批状态；保留概率解释及诊断',
    'boundary': '条件关联，不解释为因果效应', 'relation': '主要方案',
    'purpose': 'planned', 'execution_route': 'project_script',
}
```

全部文本字段须有实际含义；mapping 每项都含 field/definition/unit/time/source/version，controls/fixed_effects/data_gaps 为列表。结果后新增或改变方案另填真实 `exploration_reason`，由工具保存为 exploratory。运行中的同一方案技术修复不重新登记方案。

### 常见处理

把 recipe 放入对应方案的 `preprocessing` 字段，再保存已确认版本：

```python
from econbiz.project_scripts import (
    save_preparation_script, execute_project_script, import_script_output,
)
save_preparation_script(w, 'prepare-code', preparation_plan_id,
    recipe=recipe, inventory_id=inventory_id, reason='实现已授权的数据处理')
prepared = execute_project_script(w, 'prepare-001', 'prepare-code')
if prepared['execution_status'] == 'completed':
    source = import_script_output(w, 'processed-v1', 'prepare-001',
                                  'processed.csv', reason='登记处理后数据及来源')
    inventory = w.audit('processed-inventory', 'processed-v1',
                        entity='firm', time='year', numeric=['leverage_w', 'ln_assets'])
```

这里登记的是处理字节与来源链，不是统计认证。`save_preparation_script` 只接收未改写的工具生成代码并核对方案中的同一规则；这种纯处理不会被误记为已看到回归结果。自行编写的任意项目脚本按可能已暴露结果保守记录。

需要独立处理核对时调用 `econbiz.preprocessing_check.verify_preparation(raw, recipe, actual_csv)`；它使用 NumPy/pandas 参考计算，不调用主处理函数。读取返回的逐项 checks，并保存实际比较记录。缺少依赖或核验失败不能说已复核。此核对仅覆盖处理值，不证明任何回归结果。

### Agent 编写的分析代码

Agent 把完整实际源码传入接口；例如 files 可包含 `analysis.py`、辅助模块，Stata 路径可包含 `analysis.do` 和已登记的辅助 ado。输入、代码和预期输出路径不能重叠，使用安全的相对文件名。输入必须包含方案绑定的 inventory，也可加入其他已登记来源。

```python
from econbiz.project_scripts import save_project_script, write_script_report
save_project_script(w, 'analysis-code', analysis_plan_id,
    files={'analysis.py': actual_python_source}, entrypoint='analysis.py',
    inputs={'input.csv': inventory_id}, expected_outputs=['results.csv', 'sample.csv'],
    reason='实现已确认的研究设定')
run = execute_project_script(w, 'analysis-001', 'analysis-code')
report_path = write_script_report(w, 'analysis-001')
```

Python 为默认引擎。Stata 显式用 `backend='stata'` 保存 `.do` 入口，执行时提供实际 `stata_executable`；不静默替换语言。当前平台和版本范围同正式分析手册。源码在本次工作目录运行，输入按声明名称可读。输出应包含实际估计样本及方法/参数、系数、标准误、区间、必要诊断和单位说明；不能只写一张没有样本依据的表。

技术修复沿同一个 script_id 保存新代码版本，再用新 run_id 和 `retry_of=失败运行标识` 执行。此接口核对方案版本、输入与引擎未变；研究设定是否保持一致仍由 Agent 对照代码与方案核实。旧失败不删除。
代码修订会把旧运行的当前状态标为 stale；原始 failed/completed 状态、错误和日志仍保存在该运行内容及冻结目录。不要把“旧版本已过期”误写成从未执行或失败证据丢失。

## 4. 执行证据、检查与重跑

每次冻结方案、代码、输入、工具源码及环境，保存真实进程日志和预期输出。缺少输出、修改输入、超时或 Stata 未完成本次 do-file 都算失败。超时/取消终止进程组，已产生材料留存。宿主异常中断后重新打开项目会保留失败状态和结果暴露历史；先核对原目录，再新建运行重试。

| 产物 | 能说明什么 |
| --- | --- |
| project_script completed/passed | 源码已保存且输入/方案绑定检查通过；尚未说明执行或统计正确 |
| script_run completed/pending | 已实际执行、所声明文件与进程检查通过；尚未独立统计复核 |
| 内置 result completed/passed | 已执行并通过该方法所规定的独立数值复核 |

脚本生成的 verification.json、通过标签或退出码不能把 script_run 升级成正式已复核结果。`write_script_report` 是执行说明；内置正式结果报告仍用 `write_result_report`。没有覆盖的方法可交付实际输出和明确状态，并继续补相应参考检查；不要冒充已普遍核验的 DID/IV/权重/多维聚类。

处理后输出重新登记为 source 并盘点，随后以真实新字段绑定正式分析方案；已有授权的机械字段映射无需再次确认。若方法在内置范围，调用现有 execute_analysis 完成独立统计复核和正式报告。处理数据来源仍绑定原运行，输入、规则或运行证据失效会使下游过期。

冻结包中运行 `python3 -B run.py --output replay-001` 在新目录重跑；原运行不会覆盖。若原环境使用 Python `-S`，重跑同样加 `-S`。需要登记为新研究运行时调用公共执行接口。环境检查覆盖保存的 Python 包版本、平台及 Stata 官方命令身份；Stata 默认仅搜索官方 BASE 和本次工作目录。第三方代码应作为文件登记并随包保存，脚本不得另设外部 adopath、调用未登记文件或依赖动态联网数据。任意源码可以访问宿主许可范围，因此该工具不是安全沙箱，也不保证重现未声明的外部依赖。

会话记录可引用已可用的代码或来源，说明实际 run_id、路径、执行状态和检查缺口；不把待核验运行塞进要求已核验产物的 completed 任务。继续研究时读实际状态与文件，不只读上次报告快照。

保存 `session_note` 的必填对象为：summary（文本）、facts（事实对象列表）、decisions（文本列表）、outputs（版本引用列表）、open_questions（文本列表）、next_step（文本）、authorization（真实授权摘录）。版本引用格式为 `{'artifact_id': '实际标识', 'version': 实际整数版本}`。事实对象包含 id、claim、source_kind、locator、excerpt、evidence_status；程序输出使用 source_kind='program_output'、evidence_status='source_supported'，并附 source_ref 指向已登记、当前可用的实际材料。未核验运行不能直接作为要求 usable 的引用；将可读执行说明按 research_material 导入，引用该来源说明执行状态，并明确来源字节登记不等于统计核验。用户摘录使用 user_quote/reported，不伪造已核实等级或平台消息标识。
