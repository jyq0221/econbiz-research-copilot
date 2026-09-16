# 阶段 C 多模型比较与 Word 结果交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 按已确认设计在当前维护分支单写入者顺序执行，不默认启动多个 Agent。

**Goal:** 将同一研究内已核验的固定效应结果组织成可追溯比较，并交付经过数值和版式检查的可编辑 Word 文档。

**Architecture:** 用独立的结果适配器读取真实冻结运行，比较层负责变量对齐、样本与设定差异，展示层统一生成显示单元格供 Markdown 和 DOCX 使用。比较、文档和版式检查分别登记为版本产物，沿 Workspace 的依赖链失效。

**Tech Stack:** Python 3.9+、现有 unittest/Workspace/统计运行；DOCX 使用 python-docx 可选依赖。开发文档验收使用宿主 documents Skill 的打包 Python 与 render_docx.py；产品不依赖开发者本机绝对路径或安装该 Skill。

---

## 约定与当前基线

仓库根：`/Users/jiang/econbiz-research-copilot`。下文路径均相对此根。

设计：[已确认范围](../specs/2026-09-16-stage-c-comparison-word-design.md)。当前版本 0.2.0a3，维护分支 codex/framework-foundation；本轮验收运行 244 项，其中 212 通过、32 跳过。真实 Stata 和宿主验收必须另行实际执行，不沿用该数字声称通过。

当前可直接复用：result.content 的 plan/spec/result/sample/verification/package/input_sha256；sample.sample_keys/steps/periods；Workspace._stage/_publish；Project.require_usable 与依赖失效。

注意三处约束：

- 当前线性估计器对吸收/共线报错，不能将失败运行变成有效表列；有效运行遗漏已声明参数应报证据错误。
- 当前结果没有统一 R² 字段，首批不增加推算的 R²；仅显示当前实际有且口径明确的统计量。
- `require_usable` 校验文件和依赖，但比较消费者还须核对结构化记录与冻结输出的一致性，不能仅信任外层 passed 标签。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `econbiz/comparison_input.py` | 验证正式运行，提取参数、变量说明、样本键和来源 |
| `econbiz/comparison.py` | 比较契约、对齐与样本差异、保存/重开比较 |
| `econbiz/comparison_display.py` | 舍入、星号、显示单元格、Markdown 预览 |
| `econbiz/word_report.py` | 可编辑 DOCX、来源附录、文档产物保存 |
| `econbiz/document_checks.py` | DOCX 数值文本核对、渲染证据及逐页检查记录 |
| `tests/test_comparison_input.py` | 真实运行接入及拒绝边界 |
| `tests/test_comparison.py` | 样本、变量、版本与比较行为 |
| `tests/test_comparison_display.py` | 精确边界、显示状态、文本转义 |
| `tests/test_word_report.py` | DOCX 内容、结构、依赖和保存失败 |
| `tests/test_document_checks.py` | 文档与检查证据绑定 |
| `tests/test_stage_c_workflow.py` | 完整 Python 与显式 Stata 工作流 |
| `docs/research-handbook/result-delivery.md` | Agent 公开调用与使用流程 |
| `docs/stage-c-validation.md` | 当前实际验收证据和未完成项 |

除有必要的进展显示和入口更新，不重构旧估计器或单次报告。

## 任务 1：建立真实运行接入与证据门槛

**Files:** 新建 comparison_input.py、tests/test_comparison_input.py；读取 execution.py、run_worker.py、files.py、tests/test_execution.py。

- [x] 复跑基线 `python3 -m unittest discover -s tests -q`，记录通过与跳过；保持所有合成材料在临时目录。
- [x] 先新增真实运行接入测试，初次运行应因模块缺失失败：

```python
import tempfile
import unittest
from pathlib import Path
from test_execution import HAS_ANALYSIS, study

@unittest.skipUnless(HAS_ANALYSIS, 'analysis extra not installed')
class ComparisonInputTests(unittest.TestCase):
    def test_extracts_actual_sample_and_coefficients(self):
        from econbiz.execution import execute_analysis
        from econbiz.comparison_input import load_checked_model
        with tempfile.TemporaryDirectory() as directory:
            w = study(Path(directory))
            run = execute_analysis(w, 'run1', 'p1')
            model = load_checked_model(w, 'run1')
            self.assertEqual(model['sample_keys'], run['content']['sample']['sample_keys'])
            self.assertEqual(model['parameters'], run['content']['result']['parameters'])
            self.assertEqual(model['run'], {'id': 'run1', 'version': run['version']})
```

- [x] 实现 `load_checked_model(workspace, run_id) -> dict`：先 require_usable，限定 kind=result、model=linear_fe、实际 completed/passed。验证登记文件，读取冻结 result/sample/spec/plan/verification 并逐项比较 content；按现有运行消费验证机制检查数值证据，不执行新主估计。
- [x] 输出 run/plan/backend/input_sha256/parameters/actual_spec/sample_keys/sample/descriptive/diagnostics/variables/source_files。变量元数据含字段、定义、单位、变换及来源；无法从现有映射或处理来源确认的字段存 null，不根据字段名猜测。保持企业代码文本及前导零。
- [x] 增加真实文件篡改、仅修改 content、未核验 script_run、描述统计、失败/过期运行的拒绝测试；缺参数、重复键、样本键不一致均报 WorkflowError。
- [x] 运行 `python3 -m unittest discover -s tests -p 'test_comparison_input.py' -v`；真实输入测试通过后提交该任务文件。

## 任务 2：比较契约、变量身份和样本差异

**Files:** 新建 comparison.py、tests/test_comparison.py。

公共接口采用下列签名；参数列由 Agent 根据研究材料填写，用户不直接编辑配置：

```python
write_model_comparison(workspace, comparison_id, *, columns, variables,
                       title, display_terms=None, stars=(), reason)
read_model_comparison(workspace, comparison_id)
compare_sample_keys(left, right)
```

`columns` 为有序字典列表，每项精确含 run_id/title/role，role 为 baseline/robustness/other。run_id 不重复，至少两列；不按 p 值重排。`variables` 为有序字典列表，每项含 id/label/definition/unit/transform/members/evidence_refs；members 为 run_id 到原字段名的映射，evidence_refs 为 `{artifact_id, version}` 引用列表。映射含因变量与全部回归变量；无法确认定义时 definition/unit/transform 可以 null，按列独立身份展示并标记未知，不自动跨列合并。元数据引用加入比较依赖。

- [x] 先加入样本集合测试并实际看到模块或函数缺失失败：

```python
def test_equal_counts_are_not_equal_samples(self):
    from econbiz.comparison import compare_sample_keys
    result = compare_sample_keys([['001', '2020'], ['002', '2020']],
                                 [['001', '2020'], ['003', '2020']])
    self.assertFalse(result['same_sample'])
    self.assertEqual(result['intersection_count'], 1)
    self.assertEqual(result['left_only'], [['002', '2020']])
    self.assertEqual(result['right_only'], [['003', '2020']])
```

- [x] 实现集合交集、左右差集，验证键结构与重复；不同实体代码体系/观察单位不自动断言样本交集有研究含义，写比较警示。
- [x] 为每对模型保存差异和现有 sample.steps 中可对应 dropped_keys 的规则证据；未被规则解释的键单列 unresolved_keys。不同输入版本只说明已知差异，不声称识别了所有变化原因。
- [x] 对齐按明确变量 id 和 members，拒绝一列一个字段重复映射、定义冲突后强合并、不存在字段及 label 冒充身份。因变量定义、单位或变换不同则按因变量身份分组出表，保留跨组说明。
- [x] 行状态固定为 estimated/not_in_model；未来有明确上游证据才允许不可估计状态。有效运行缺少应有参数视为损坏；不可用统计值显示未提供，系数 0 仍是 estimated。
- [x] 保存 schema_version=1、生成时间、列顺序、变量映射、参数原精度、实际设定、样本差异、描述统计和来源。JSON 与 Markdown 同版本写入 research/reports；dependencies 包含全部运行和元数据引用。重开时重新验证来源版本与比较内容。
- [x] 增加来源修订使比较过期、样本缺失损失、单位不同分表和完整系数保留测试。运行 `python3 -m unittest discover -s tests -p 'test_comparison.py' -v` 后提交。

## 任务 3：统一表格显示与说明

**Files:** 新建 comparison_display.py、tests/test_comparison_display.py；更新 comparison.py 的预览生成。

- [x] 先写精确 p 值边界测试并确认失败：

```python
def test_stars_use_unrounded_p_and_strict_threshold(self):
    from econbiz.comparison_display import significance_marks
    rules = [(0.01, '***'), (0.05, '**'), (0.1, '*')]
    self.assertEqual(significance_marks(0.049999, rules), '**')
    self.assertEqual(significance_marks(0.05, rules), '*')
    self.assertEqual(significance_marks(0.1, rules), '')
    self.assertEqual(significance_marks(0.001, []), '')
```

- [x] 实现 `significance_marks(p, rules)`、`format_number(value, digits=3)`、`build_display(comparison)` 和 `render_comparison_markdown(display)`；rules 限有限递增阈值和唯一非空标记，表注注明严格 p<阈值。默认无星号，不添加默认显著性筛选。
- [x] 显示系数和括号标准误，保留精确值来源；小值舍入为零时提供原精度详细记录，归一显示负零。未纳入显示“未纳入”，未知显示“未提供”，不得把这些状态写为 0。
- [x] 每列显示观测数、主体数、实际年份、控制变量、固定效应、SE 与聚类字段、引擎和状态；R² 首批不凭空生成。display_terms 只能选择合法变量 id，注明省略规则，comparison JSON 保留全部参数。
- [x] 输出有证据的设定/样本差异、按模型标注的描述统计、变量定义和来源附录；文字只说条件关联，不按星号断言稳健。Agent 自写解释作为有来源的研究笔记附入，数值引用使用运行及参数字段定位。
- [x] 测试中文长字段、Markdown 分隔符转义、因变量分组、零值与未知状态及顺序；运行 `python3 -m unittest discover -s tests -p 'test_comparison_display.py' -v` 后提交。

## 任务 4：生成并保存可编辑 Word

**Files:** 新建 word_report.py、tests/test_word_report.py；修改 pyproject.toml。

公共接口：`write_word_report(workspace, report_id, comparison_id, *, narrative_id=None)`；narrative_id 为已有可用研究笔记，可省略。内部 `render_word(display) -> bytes` 只渲染，不运行统计。

- [x] 确认并固定兼容 Python 3.9 的 python-docx 版本及许可证，加入独立 `documents` optional dependency；基础 import econbiz 不导入 docx。不把宿主捆绑路径写进产品。
- [x] 先新增 DOCX 可编辑文本测试，确认模块缺失失败：

```python
def test_docx_contains_editable_tables(self):
    import io
    from docx import Document
    from econbiz.word_report import render_word
    from econbiz.comparison_display import build_display
    content = self.comparison['content']
    document = Document(io.BytesIO(render_word(build_display(content))))
    self.assertGreater(len(document.tables), 0)
    cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    self.assertIn('观测数', cells)
    self.assertIn('72', cells)
```

测试的 setUp 使用任务 1 的 study/execute_analysis 创建两个运行，再按任务 2 的完整契约保存 self.comparison；不得伪造 passed 运行供集成测试使用。

- [x] 设置 A4、明确东亚字体、正文 10.5–11 pt、表格不小于 9 pt；默认 1–3 模型列纵向，4–6 列横向，超过 6 列按最多 6 列分组。中文标签列至少 35 mm，关闭自动列宽，表格无竖线，顶线/表头底线/末行底线三线；按实际渲染修订列容量。
- [x] 设置重复表头，行内避免分页，表题与首行保持，表注随分表重复；在每组模型表后写设定、样本差异、变量定义与来源。长定义放定义表，不挤进系数行。
- [x] 从同一 display 渲染，附生成时间、比较版本和每列运行/方案版本；DOCX 为静态快照。先生成全部字节再 `_stage/_publish`，依赖比较与 narrative；保存失败不覆盖旧版本。
- [x] 文档产物记录 generated、numeric_text_check、render_check、visual_check 分项状态；生成成功不自动写 visual passed。缺依赖抛可理解的 WorkflowError，旧比较继续可读。
- [x] 运行 `python3 -m unittest discover -s tests -p 'test_word_report.py' -v`，覆盖方向、分组、表头、无图片化表格、依赖过期和缺包；通过后提交。

## 任务 5：绑定数值检查与版式证据

**Files:** 新建 document_checks.py、tests/test_document_checks.py；更新 word_report.py。

公共接口：`check_word_content(docx_bytes, display)` 返回逐单元格核对；`record_document_review(workspace, review_id, report_id, *, render_files, inspected_pages, findings, reason)` 保存实际渲染和人工/Agent 视觉观察，不以自动文本扫描替代视觉检查。

- [x] 先用生成 DOCX 通过数值文本检查，再用 python-docx 修改一个系数单元格，测试检查失败；自报 passed 字段不能覆盖检查结果。
- [x] 逐表匹配列编号、参数行、统计行及单元格值；核对逻辑不调用 render_word 重建文件代替读取真实 DOCX。显示精度之外的精确值仍由比较与运行负责。
- [x] review 绑定 report 版本及 DOCX SHA-256；逐页图片和可选 PDF 使用项目文件引用保存；inspected_pages 必须恰好覆盖实际渲染页号，findings 非空不能标为视觉通过。记录观察者声明和时间，不认证观察者身份。
- [x] 修改文档、缺页、额外页、只检查首页、失效的比较、篡改图片均不能沿用旧通过记录。`check_status` 指文件契约通过，视觉状态使用独立字段，不能回写统计运行状态。
- [x] 在 documents Skill 指定打包环境用 render_docx.py 渲染三列纵向、六列横向、八列拆表和长变量跨页四组案例，打开每页 PNG，修复后重新渲染。保存页数、字节散列、发现及最终实际状态。
- [x] 运行 `python3 -m unittest discover -s tests -p 'test_document_checks.py' -v` 后提交；开发渲染使用宿主环境，用户环境缺渲染能力时保留 not_performed，不谎称完成。

## 任务 6：公开流程与接续

**Files:** 新建 docs/research-handbook/result-delivery.md；修改 .agents/skills/econbiz-research/SKILL.md、econbiz-analysis/SKILL.md、econbiz-interpret/SKILL.md、docs/research-handbook/project-analysis.md；视显示需要修改 econbiz/progress.py 及测试。

- [x] 手册给出完整的 write_model_comparison → write_word_report → 检查 → 重开示例；每个字段与前述接口一致，示例只引用实际用户项目，不把合成授权当用户授权。
- [x] 入口明确自动读取现有结果、保留模型角色与顺序，材料不足先完成可做事实检查；不为出表重跑模型，不让用户选择统计库或填写机器 JSON。
- [x] 接续展示比较版本、文档路径、数值/渲染/视觉状态、过期原因和下一步。未核验脚本作为独立附件，不能被 Agent 写成正式已核验列。
- [x] 用 `python3 scripts/sync_skills.py` 同步普通副本，运行 `python3 scripts/sync_skills.py --check` 及相关入口测试后提交。

## 任务 7：完整流程与分发验收

**Files:** 新建 tests/test_stage_c_workflow.py、docs/stage-c-validation.md；修改 tests/test_distribution.py、tests/test_skills_package.py，验收完成后更新 README.md 与版本说明。

- [x] 临时真实合成项目依次执行三个预先设定模型：基准、增加控制变量、明确限制年份；比较/Word/检查/重新打开，断言源文件不改、所有数值可追溯。
- [x] 构造控制变量缺失、同 N 不同键、同名不同单位与不同因变量变换案例；失败来源不得进入比较。另用实际 Stata 运行混合 Python 列，只有显式环境启用原生，不默认探测 Stata。
- [x] Python-only 流程禁止 Stata 运行导入/发现/启动；无 documents 依赖仍可打开基础研究与比较 JSON，无统计依赖时各统计测试明确跳过。
- [x] 从公开入口和手册执行自然语言任务，实际生成 Word 并续接；宿主测试使用可用独立会话工具，若缺能力则记录未验收，不以单元测试代替，也不擅自启动子 Agent。
- [x] 运行 `python3 -m unittest discover -s tests -q`、`python3 -S -m unittest discover -s tests -q`、`python3 scripts/sync_skills.py --check` 和 `git diff --check`；记录实际总数、跳过原因与环境。
- [x] 在临时归档与普通本地 clone 的使用文件树中使用已安装的固定版本 analysis/documents，完成真实比较、Word、重开；验证文件逐字节匹配、链接可解析，不含个人研究和开发材料。对外发布及公开 URL 下载复验须待发布授权，不冒充已发布。
- [x] 按最终实际结果写 stage-c-validation.md，引用证据位置、测试与视觉结果和未完成条件；通过后更新 README 能力边界。提交开发成果，报告尚未发布。

## 计划自检

- 设计的模型比较、样本解释、Word、版本追溯分别对应任务 1–3、2、4–5、2/5/6。
- 原始精度、无自动模型筛选、变量定义未知、宽表、可编辑性和真实宿主测试均有验收位置。
- 统计通过与文档通过分开；不增加通用方法认证，不增加不真实的 R² 或吸收结果。
- 实施中如发现已确认范围内的接口问题，可修正技术方案并记录；改变首批统计方法或研究行为时再说明实质变化。

## 执行交接

用户已确认并要求开始，现已按七项任务顺序完成首批实现。开发版本 0.3.0a1。任务内提交合并为收尾集中提交；review 改为必需 PDF 以获取实际页数。无新的主估计范围或发布动作。验收、初次失败及复测证据见 [阶段 C 记录](../../stage-c-validation.md)。上面的清单按实现和等效验收完成标记；具体实际覆盖以验收记录和测试文件为准。
