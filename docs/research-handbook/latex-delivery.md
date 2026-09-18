# LaTeX 结果与 PDF 交付

用户可以直接说：“把已有回归结果整理成 LaTeX 和 PDF，附上模型公式与结果说明。”Agent 负责读取材料、调用以下接口并检查输出；不要求用户填写程序配置。

首版接收同项目中已独立核验的线性固定效应运行，来源可为 Python 或 Stata。可导出单模型，或沿用[模型比较](result-delivery.md)中的列顺序、变量映射和星号规则。描述统计取自各模型实际样本。整理结果不会重新估计，脚本或外部表格不会因排版升级为已核验结果。

## 1. 环境

源码生成复用现有 analysis 依赖。PDF 结构和逐页证据检查另需 `.[latex]`，其中包含 pypdf/Pillow；外部编译环境需要 XeLaTeX 及 ctex、Fandol、geometry、amsmath、amsfonts、booktabs、tools、pdflscape 宏包。可以使用已有 TeX Live、MacTeX 或便携 TinyTeX；编译时不会自动安装或下载依赖。

先检查宿主中是否有 `xelatex`；没有时完成依赖配置再编译。显式配置使用可执行文件的实际绝对路径，不将开发者电脑路径写入研究项目或通用示例。保留 `xelatex` 文件名，不能把它的符号链接解析成 `xetex` 后调用。

缺编译器时源文件仍能保存，编译失败记录会说明原因；不能称为“PDF 已生成”。真实 PDF 验收还需要宿主可用的 PDF 页面渲染工具。

## 2. 生成源文件

```python
from econbiz.workspace import Workspace
from econbiz.latex_report import write_latex_report
from econbiz.latex_checks import read_latex_report

w = Workspace.open(project_path)
report = write_latex_report(w, report_id, run_id=checked_run_id)
report = read_latex_report(w, report_id)
print(w.last_receipt)
print(report['files'])
```

上述标识由 Agent 从当前项目取得。已有比较时将 `run_id=checked_run_id` 替换为 `comparison_id=checked_comparison_id`，两个来源参数只能指定一个。单模型默认全部系数、无星号；多模型沿用比较记录中的展示规则。

默认 `language='zh-CN'`，英文交付用 `language='en'`。语言参数控制内置标签与说明，实际变量标签、定义、来源题名及研究笔记保留输入文字；Agent 应先完成用户要求的语言整理并保存，再导出，不能把改变标签语言当成正文翻译已经完成。

结果说明通过 `narrative_id` 引用有效的 `session_note`。按[记录规则](project-records.md)保存前，Agent 须核对数值、单位、实际样本与解释依据。文档检查只确认登记文字忠实输出，不认证自由文字的推导或因果判断。

输出包含 `main.tex`、`tables.tex`、`narrative.tex`、`equations.tex`、`sources.tex`、`README.md` 与 `delivery.json`，按研究报告目录的标识和版本保存。单独使用表格片段时，需要主文件中的 EBCell/EBText 等宏定义及所列宏包。

## 3. 公式

将真实模型设定整理成公式条目，再用 `equations=equations` 传入。一个条目的结构如下；示例只适用于实际含 x、c 及企业/年度固定效应的设定：

```python
equations = [{
    'id': 'model',
    'title': '模型设定',
    'latex': r'y_{it}=\beta x_{it}+\gamma c_{it}+\mu_i+\lambda_t+\epsilon_{it}',
    'explanation': '符号对应实际方案中的因变量、解释变量、控制变量和两类固定效应。',
    'source_refs': [{'artifact_id': actual_plan_id, 'version': actual_plan_version}],
}]
```

每条公式必须有唯一标识、标题、数学源码、解释和至少一个当前方案/研究笔记的版本引用。Agent 核对公式与实际设定的对应关系；语法通过不认证经济或数学含义。

支持上下标、分数、根号、求和、希腊字母、常用运算符和括号。例如 `\frac{1}{N}\sum_{i=1}^{N}x_i`。长度上限 4096 字符，分组深度上限 32；希腊字母用数学命令。首版不接受任意宏定义、文件命令、多行环境或外部 `.tex` 文件。正文中的特殊字符按文字显示。

## 4. 实际编译

```python
from econbiz.latex_runtime import compile_latex_report
from econbiz.latex_checks import read_latex_build

build = compile_latex_report(w, build_id, report_id)
# 编译器不在 PATH 时可传 executable=actual_xelatex_path。
build = read_latex_build(w, build_id)
print(build['content']['compile_check'], build['content']['error'])
print(build['files'])
```

编译在临时目录执行两至三遍，总超时默认 120 秒，可通过 `timeout` 调整。源文件、引擎版本、选项、退出状态、日志和 PDF 散列一并记录。所有重试保存为新版本；不会把旧 PDF 当成本次输出。

只有本次编译成功、辅助文件稳定且 PDF 可以解析，才标记 `compile_check='passed'`。成功生成 `report.pdf`；失败保存 `compile.log` 与失败记录，源文件和历史产物保留。读取失败记录允许检查原因，不允许把它当成成功 PDF。

若编译中来源变化，本次尝试失败。失败记录以冻结来源引用保留证据，无需已失效来源重新通过依赖校验；它自身始终不可作为成功输出消费。成功记录正常绑定依赖，上游变化后失效。编译结束时如果项目状态文件损坏，不覆盖该状态。

## 5. 逐页检查

编译通过之后，宿主将这次 `report.pdf` 渲染为 PNG，打开每一页检查中文、公式、数字、宽表、表头和表注。日志警告也要核对；退出码为零不等于版式通过。

```python
from econbiz.latex_checks import record_latex_review, read_latex_review

review = record_latex_review(
    w, review_id, build_id,
    pages=actual_ordered_page_paths,
    inspected_pages=list(range(1, actual_page_count + 1)),
    findings=actual_findings,
    reason='保存实际逐页观察',
)
review = read_latex_review(w, review_id)
```

图片须命名为 `page-1.png` 起的连续页码，与 PDF 页数一致。`actual_findings` 是实际发现的问题列表，确认没有问题才用空列表。渲染工具出现缺字或语言映射错误时，应先修复渲染环境，不能登记视觉通过。

`latex_report` 的通过只代表源码内容核对；`latex_build` 的通过代表编译与 PDF 结构；`latex_review` 的 `visual_check` 单独表示观察结果。文件检查不认证观察者身份或图片与 PDF 的像素对应关系。没有实际查看全部页面，不能调用接口声称已检查。

## 6. 保存与接续

使用 `read_latex_report`、`read_latex_build`、`read_latex_review` 检查当前有效材料。`研究进展.md` 和恢复上下文会列出源码、PDF 与检查记录；所有交付保持版本和来源绑定。旧外部副本不会随研究结果自动更新。

最终交付以 `.tex` 源文件和成功编译的 PDF 为主；页面图片与日志留作项目内检查证据。保存结束时检查回执，注明实际完成范围。完整论文组织、文献数据库和期刊模板不属于首版接口。
