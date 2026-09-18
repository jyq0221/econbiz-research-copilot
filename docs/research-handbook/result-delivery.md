# 多模型比较与 Word 交付

需要 LaTeX 源文件、公式或 PDF 时使用 [LaTeX 结果交付](latex-delivery.md)，可复用本页建立的比较记录，也可直接导出单个已核验运行。

先读取当前项目的研究记录、方案和实际运行，确定用户要展示的基准、稳健性及顺序。首批正式比较支持同项目的已独立核验线性固定效应结果，可混合 Python 与 Stata；不启动新的估计。项目脚本和外部表格仍分别展示实际执行/尚未复现状态，不能成为正式已核验列。

交付语言按用户本次请求及明确指定确定，已有明确偏好持续有效。正文、表题、表注、图注与结论采用交付语言，字段标识、来源题名和追溯信息保留原文。当前内置 Word 模板主要为中文；需要其他语言时，Agent 应完成相应语言的最终材料并保存为新版本，重新核对数值、文字及版式，不能把原中文文档的检查结论直接移用于翻译稿。

## 1. 先读取实际来源

```python
from econbiz.workspace import Workspace
from econbiz.comparison_input import load_checked_model
w = Workspace.open(project_path)
models = [load_checked_model(w, run_id) for run_id in selected_run_ids]
```

`project_path` 与 `selected_run_ids` 由 Agent 从用户指定项目和实际记录取得。运行读取会检查登记字节、冻结样本与当前版本，并独立复核数值；不会重新执行主估计。Python-only 使用不启动或发现 Stata。

模型角色来自已有研究记录或用户要求，不能按显著性选列。追加共同样本、新模型或改变变量属于分析方案变更，按已有授权规则另行处理。

## 2. 建立完整变量身份

columns 是有序列表，每项为 `dict(run_id=实际运行标识, title=可读列标题, role='baseline'/'robustness'/'other')`。至少两列，运行不重复。

variables 必须覆盖每个模型的因变量及全部解释/控制变量。每项完整字段为：

```python
variable = dict(
    id=variable_id, label=display_label, definition=definition,
    unit=unit, transform=transform,
    members={run_id: field for run_id, field in confirmed_members},
    evidence_refs=[dict(artifact_id=source_id, version=source_version)
                   for source_id, source_version in evidence_versions],
)
```

上述值由 Agent 阅读真实材料后填写；这是接口结构，不是要求用户补写代码。id 是唯一字母/数字/下划线/连字符标识；成员显式对应运行到实际字段。来源引用可指向已保存字段说明、处理记录或研究笔记，必须为当前有效版本；没有额外来源可用空列表，但映射仍仅是调用者的明确声明。

已知定义/单位与冻结方案不能冲突。definition/unit/transform 未知时使用 None，未知身份分别按列登记，不能共享 id。转换可写“原值”“ln(资产)”等经材料确认的口径，不能仅根据列名猜。因变量口径不同用不同身份，报告自动分组；因变量和解释变量不共用身份。同一原字段在同一模型只能映射一次。

## 3. 保存比较并生成 Word

```python
from econbiz.comparison import write_model_comparison, read_model_comparison
from econbiz.word_report import write_word_report
comparison = write_model_comparison(
    w, comparison_id, columns=columns, variables=variables,
    title=report_title, reason=selection_reason,
    display_terms=None, stars=(),
)
word = write_word_report(w, word_report_id, comparison_id)
print(w.last_receipt)
print(word['files'])
```

首批统计依赖沿用 analysis，Word 另用 `python-docx==1.2.0`：安装项目的 `.[analysis,documents]`。基础研究保存不依赖 Word。不能把开发者的本机运行环境路径写入用户项目。

默认显示全部解释变量，不显示星号。如用户需要，stars 使用 `[(0.01,'***'),(0.05,'**'),(0.1,'*')]`，以未舍入 p 值按严格小于阈值判断。display_terms 仅可指定解释变量身份列表；省略规则写入表注，所有原参数仍保留。实际没有的 R² 不补造。

样本比较使用实际企业年度键，并保留各步排除规则；同 N 不能当作同一样本。不同数据版本的主体编码与观察单位要另外核实；原因不明就标尚未定位。系数变化不能单独归因于控制变量或显著性变化。

模型表每组最多六列；三列以内纵向，四至六列横向，更多列拆表。变量定义、每列同样本描述统计和来源附录随文档保存。默认简短说明限定于有证据的条件关联。需要研究者风格的解释时，先按记录手册保存有来源的 session_note，再传 `narrative_id=笔记标识`。保存笔记前，Agent 必须将每个数值引用定位到实际运行及参数字段，核对原精度和含义。工具核对文字是否忠实进入文档，不自动认证自由文本中的数值推导、方法或因果主张。

## 4. 内容与逐页视觉检查

```python
from econbiz.document_checks import read_word_report, record_document_review
word = read_word_report(w, word_report_id)
```

Word 产物的 completed/passed 指文件及数值文本契约通过。`numeric_text_check`、`render_check`、`visual_check` 分开；刚生成文件的后两项为 not_performed。

宿主有文档工具时，按文档工具流程把当前 DOCX 渲染为 PDF 与逐页 PNG，打开全部页面，修正缺字、裁切、重叠、表头和分页问题。渲染依赖本机可用字体；仅提取 XML 文字不能证明字体显示正常。缺少渲染能力可以保存 DOCX，但必须说明版式未验收。

实际渲染并看完全部页面后才能记录：

```python
review = record_document_review(
    w, review_id, word_report_id,
    render_files=dict(docx_sha256=word['content']['docx_sha256'],
                      pdf=rendered_pdf_path, pages=ordered_page_png_paths),
    inspected_pages=list(range(1, actual_page_count + 1)),
    findings=actual_findings, reason='记录实际逐页检查',
)
```

检查记录另需 `.[document-review]`，包含 pypdf 与 Pillow。图片按实际页次命名 page-1.png 起；页数从实际 PDF 读取。findings 是实际问题的文本列表，确实没有问题才用空列表。接口核对文件、页数和 DOCX 散列，视觉内容是调用者观察声明，不能用它伪造逐页验收；它不认证渲染像素与文档的因果关系或观察者身份。

Word、比较和 review 分别版本化。上游改动使下游过期；旧 DOCX 仍是生成时快照，不会自动改变已发送的文件。新报告须新一轮检查，不沿用旧图片。交付用户最终 DOCX，临时 PNG/PDF 留在检查证据中；除非用户要求，不把中间文件作为额外交付。

## 5. 收尾和接续

重新打开项目后用 read_model_comparison、read_word_report 核对，不仅查看外层标签。用 `read_document_review(w, review_id)` 核对 document_review 的当前有效性和独立视觉状态。用 session_note 保存交付标识、实际完成范围和下一步，检查保存回执。存在失败或未做的检查如实说明，不把排版完成写成统计或因果认证。
