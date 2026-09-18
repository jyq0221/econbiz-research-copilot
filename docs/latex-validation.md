# LaTeX 结果交付验收

日期：2026-09-18。维护分支：`codex/framework-foundation`。对应[设计](superpowers/specs/2026-09-18-latex-result-delivery-design.md)与[公开使用手册](research-handbook/latex-delivery.md)。

功能代码本地提交：`c9b71c4`。

## 已实现

单模型与已有多模型比较可以导出五个可编辑 TeX 文件及交付记录；支持结果说明、带来源的公式、中英文内置标签、宽表和长表。新增实际 XeLaTeX 编译、失败尝试保留、严格读取与逐页检查记录，并纳入项目进展与恢复。统计数据沿用当前已核验运行，导出不触发新估计。

实现分为结果适配/渲染、受限文本和数学语法、实际内容检查、原生编译及页面证据。英文标签独立放在 `comparison_english.py`，不改变既有中文 Word/Markdown 的默认数据。

## 自动化验收

环境：macOS arm64，Python 3.9.6，pypdf 6.10.2，Pillow 11.3.0；项目固定分析依赖。实际 Stata 19 和 XeTeX 0.999998 / TeX Live 2026 均启用。

完整项目验证：

```sh
ECONBIZ_TEST_XELATEX=<实际XeLaTeX路径> \
ECONBIZ_TEST_STATA=<实际Stata路径> \
ECONBIZ_STATA_EXECUTABLE=<实际Stata路径> \
python3 -m unittest discover -s tests
```

结果：**289 tests，266.374 秒，OK，无跳过**。本次新增 18 项 LaTeX 测试，覆盖源文件数值、转义、公式、实际内容核对、来源/文件篡改、失败编译、超时、重试、来源变化、警告、原生 PDF、逐页记录和临时 clone/ZIP。

公式允许列表审查另发现无效的 `\infinity` 名称：先增加失败断言，再去除该名称；`\infty` 正常支持。对应公式测试再次通过。最终源码、临时 clone/ZIP 原生编译和 Skills 包共 13 项复核通过（11.462 秒）。两套 Skills 同步检查、差异格式检查通过。

基线比较测试 6 项、既有 Word 导出测试 5 项、进展恢复测试 4 项也分别通过，随后纳入完整项目检查。没有把模拟编译器测试当作原生 PDF 验收。

## 原生 PDF 与逐页视觉检查

便携编译环境位于本次临时目录，来源为 TinyTeX 官方 v2026.09 macOS 发布包，安装 ctex、Fandol、xeCJK 与 pdflscape 等依赖；未改变系统 TeX 配置。产品中没有固定该机器的可执行路径。来源：[TinyTeX 发布](https://github.com/rstudio/tinytex-releases/releases/tag/v2026.09)、[CTeX](https://ctan.org/pkg/ctex)、[Fandol](https://ctan.org/pkg/fandol)。

在临时合成项目实际执行 7 个已核验运行，样本为 72 个企业年度观测，其中第二个运行由 Stata 执行，其余使用 Python。三套最终输出均经过严格读取、原生编译和全部页面观察：

| 样例 | 最终版本 | 页数 | 覆盖 |
| --- | --- | ---: | --- |
| wide | 源码/PDF v3 | 6 | 七模型拆表、六列横向、跨页重复表头、长中文标签、特殊字符、星号、说明、公式、混合引擎 |
| single-en | 源码/PDF v3 | 2 | 单模型、英文内置标签、原始中文定义保留、公式及来源 |
| demo | 源码/PDF v1 | 3 | 三列纵向、常规标签、结果说明、希腊字母、分数与求和 |

最终 PDF 的 SHA-256：

- wide：`85cc6002c17b2d4a964710939e91230d97868eace87eb9d1b39fb7b540125fa4`
- single-en：`3e29b0632185d0330b3b38ae570c6eb01e839d383c6444882325d0efc0f3319b`
- demo：`0ed75cbece6b577b0a2f0d4b46644d70acc66bdffd989bd17effb726a5cde27a`

最初页面观察发现横向报告标题独占一页、表注与表题孤立；增加回归用例后，将报告标题置于首表所在页面、表题纳入表头、表注纳入 longtable 最后一页表尾。来源附录调整为紧凑字号及段距，避免最后一个来源独占末页。最终重新编译并打开全部 11 页，未见缺字、裁切、重叠；最终编译警告列表均为空。跨页表和来源信息未因排版删除。

宿主 Poppler 的中文映射配置缺失，初次渲染输出错误，未用于验收。最终使用宿主已带的 PDFium 渲染，逐页图片和观察通过公共接口保存，重新打开后读取一致。源码、编译与视觉状态相互独立。

本次本地证据根目录：`/private/tmp/econbiz-latex-qa-20260918-compact/`，其中 `study/research/reports/` 保存版本产物与检查记录。全套测试日志：`/private/tmp/econbiz-latex-tools/full-tests.log`。这些是本次临时证据位置，不是产品路径配置，临时目录清理后可能不再保留。

## 设计落实与检查边界

- 编译期间上游失效时，成功依赖规则会阻止保存失败尝试；现实现让失败记录保留冻结来源引用并始终标为失败，成功编译仍绑定正常依赖。真实回归测试确认不会覆盖并发发生的已保存上游更正。
- 成功 PDF 必须来自本次临时目录，退出码、两至三遍辅助文件稳定性、PDF 结构与散列均核对；重试保留历史。项目状态损坏时停止保存，不覆盖损坏状态。
- 原生宽表验收的早期 288 行/25 变量合成估计，在现有 linearmodels 的双向去均值矩阵乘法处触发 `divide by zero encountered in matmul`。独立的有限矩阵乘法复现了环境告警，`einsum` 收缩得到有限值；本次未修改统计引擎、未抑制告警，也未使用该失败运行作为通过证据。最终版式测试使用原有已通过独立核验的 72 行夹具，以长标签触发跨页。这一既有数值环境问题未在本次 LaTeX 工作中修复。
- 新增 Skills 路由和公开接口经过静态路径、同步与真实程序流程验收；未另行执行新宿主会话的自然语言行为测试，不据此宣称所有 Agent 宿主已验收。
- 完整论文、参考文献管理、外部 TeX 修改、任意估计方法接入仍不在首版范围。
- 实施验收当时保留开发分支，未更新公开 main/ZIP；随后用户明确要求“更新”，已发布 0.3.0a2 并从 GitHub 实际下载复验，见[发布检查](latex-release.md)。
