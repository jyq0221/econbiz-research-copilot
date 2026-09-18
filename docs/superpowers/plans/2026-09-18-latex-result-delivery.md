# LaTeX 结果交付实施计划

> **For agentic workers:** Use executing-plans to implement this plan task-by-task. 按用户授权在当前开发分支顺序实施，测试均为临时合成项目；不另开研究或自动启动多个 Agent。

**Goal:** 从当前已核验结果导出 LaTeX、真实编译 PDF，并支持检查与接续。

**Architecture:** 结果适配与语法渲染、独立内容检查、限时编译、页面审阅分别负责。复用 Workspace 的版本和依赖，不重跑估计；保持 Word 默认行为。

**Tech Stack:** Python 3.9 标准库、现有分析接口、XeLaTeX/CTeX/Fandol/booktabs/longtable、pypdf/Pillow。

## 1. 源文件与语法

Files: `econbiz/latex_syntax.py`, `econbiz/latex_report.py`, `econbiz/latex_checks.py`, `tests/test_latex_report.py`。

- [x] 先写失败用例：`assertIsNotNone(find_spec('econbiz.latex_report'))`；合成真实运行导出并重新打开，独立断言系数/样本行；特殊字符 round-trip、公式拒绝文件命令和错误分组、来源变更失效。
- [x] 执行 `python3 -m unittest discover -s tests -p 'test_latex_report.py' -v`，确认缺模块失败。
- [x] 实现公共调用 `write_latex_report(w, 'tex', run_id='r1', equations=[...])` 和 `read_latex_report(w, 'tex')`；多模型调用 `comparison_id='cmp'`。两来源互斥，沿真实模型建立统一 display。保存五个 tex、README、delivery.json。
- [x] 文本逐字符转义；公式使用命令白名单、分组校验及长度深度限制。检查器解析固定 Cell/Text 块，核对实际内容，而非只重新渲染后比较。
- [x] 运行来源/转义/公式/篡改/语言测试及现有比较、Word 测试，全部通过后提交本阶段。

## 2. 编译与读取

Files: `econbiz/latex_runtime.py`, `econbiz/latex_checks.py`, `tests/test_latex_runtime.py`, `pyproject.toml`。

- [x] 先写缺编译器、失败日志、超时、PDF 损坏、来源变更与成功重开测试，确认尚无编译接口而失败。
- [x] 实现 `compile_latex_report(w, 'pdf', 'tex', executable=path, timeout=120)`，独立临时目录和限时参数列表；两至三遍编译，保留引擎/日志/辅助文件稳定性与 PDF。
- [x] 实现 `read_latex_build`，失败记录可读，成功必须实际核对 PDF/日志及源文件；新重试保留历史。
- [x] 添加 `latex = ['pypdf==6.10.2', 'Pillow==11.3.0']` 可选依赖，不自动安装外部 TeX。
- [x] 执行 `python3 -m unittest discover -s tests -p 'test_latex_runtime.py' -v`，通过失败路径和真实 XeLaTeX 用例后提交。

## 3. 页面检查与接续

Files: `econbiz/latex_checks.py`, `econbiz/progress.py`, `tests/test_latex_review.py`。

- [x] 先测试未经编译不能审阅，页数/图片顺序/散列错误拒绝，以及重新打开恢复源码/PDF链接；确认失败。
- [x] 实现 `record_latex_review(w, review_id, build_id, pages=paths, inspected_pages=[1,...], findings=[], reason=...)` 和严格读取；记录当前 PDF 及全部页面，观察与文件验证分开。
- [x] 接入 progress 的严格读取和交付显示，失败编译保留状态，旧 Word 分支保持行为。
- [x] 运行 `test_latex_review.py`、`test_progress.py`、`test_stage_c_workflow.py`，通过后提交。

## 4. 文档、分发与完整验收

Files: `docs/research-handbook/latex-delivery.md`, `docs/research-handbook/result-delivery.md`, `README.md`, `README.en.md`, `.agents/skills/econbiz-interpret/SKILL.md`, `.agents/skills/econbiz-research/SKILL.md`, `tests/test_distribution.py`, `docs/latex-validation.md`。

- [x] 增加公开使用树的临时 clone/ZIP 源码、真实编译和重开测试，先确认缺少分发接口或说明的失败。
- [x] 写入实际可用的调用示例、公式结构、依赖配置、失败/版式边界；同步 Skills。
- [x] 在临时目录准备真实 XeLaTeX 环境；生成中文/英文、单列/六列/超过六列/跨页表/特殊字符/公式样例并编译。将所有 PDF 渲染为图片，逐页检查并记录。
- [x] 执行 `ECONBIZ_TEST_STATA=/Applications/Stata/StataMP.app/Contents/MacOS/stata-mp ECONBIZ_STATA_EXECUTABLE=/Applications/Stata/StataMP.app/Contents/MacOS/stata-mp python3 -m unittest discover -s tests`；执行 `python3 scripts/sync_skills.py --check` 和 `git diff --check`。
- [x] 对照已批准设计审查最终代码，修复影响内容/状态/编译正确性的问题，按改动补回归验证；记录真实通过/跳过数量、引擎版本和页面检查结果。
- [x] 更新设计实施状态和本计划，提交开发分支。用户未要求公开发布，此次不推送 main/ZIP。

## 实际收尾

已按用户批准范围完成。完整项目 289 项测试无跳过通过；真实 XeLaTeX 和 Stata、临时 clone/ZIP、11 页视觉检查均有证据。代码和说明按两次本地提交保存，阶段任务在同一开发分支连续完成。测试细节及实现调整见 [验收记录](../../latex-validation.md)。Skills 本次仅做路由/同步/程序检查，独立宿主会话行为另行验收。
