# 阶段 C 验收记录

日期：2026-09-16。开发版本：0.3.0a1。维护分支：codex/framework-foundation。所有数据和运行均为临时合成测试，没有新建用户个人研究；实施验收当时尚未发布；后续授权发布与公网复验见下文。

## 已实现范围

- 正式运行适配：只接收实际完成并独立复核的线性固定效应结果；逐项核对冻结计划、设定、输入、输出、样本和复核证据。
- 多模型比较：保留指定角色、顺序、原始精度和全部系数；按明确变量身份对齐；不同因变量身份分表；实际企业年度键交集、差集和排除规则可追溯。
- Word 交付：可编辑三线表、变量定义、每列同样本描述统计、来源版本；三列以内纵向、四至六列横向、更多列拆表。默认不加星号，不按显著性筛模型。
- 文档核对：读取实际 DOCX 的单元格、表注、段落顺序和额外文字。生成、数值文本、渲染、视觉结论分开记录；版式证据保存为独立版本并绑定当前 DOCX 散列。
- 接续：严格读取比较、Word 和版式记录；上游更改或结构化内容与登记文件不一致时提示重新核对。

公开调用见 [结果交付手册](research-handbook/result-delivery.md)。首批不接收未独立核验的外部回归表或任意项目脚本作为正式比较列；不扩展 DID、IV、R² 或不可估计参数的统计契约。

## 自动检查

环境：macOS arm64，系统 Python 3.9.6；numpy 2.0.2、scipy 1.13.1、pandas 2.3.3、linearmodels 6.1、python-docx 1.2.0、pypdf 6.10.2、Pillow 11.3.0；原生引擎 Stata 19。

| 检查 | 实际结果 |
| --- | --- |
| `ECONBIZ_TEST_STATA=实际入口 python3 -W error -m unittest discover -s tests -q` | 271 项，268 通过、3 跳过，150.757 秒 |
| `ECONBIZ_STATA_EXECUTABLE=实际入口 python3 -W error -m unittest discover -s tests -p test_project_scripts_native.py -q` | 3 项全部通过，6.842 秒 |
| `python3 -S -m unittest discover -s tests -q` | 271 项，155 通过、116 跳过，8.923 秒 |
| Skills 同步、`git diff --check` | 通过 |

合计 271 项均已覆盖通过，无未完成测试。第一轮全套复测的三项跳过是通用原生项目脚本测试，使用不同显式环境变量启用，因此单独补测。`-S` 不载入 site-packages，跳过可选统计、文档及原生测试；这不是统计功能通过的证据。日志：final-tests-retry.log、final-native-scripts.log、final-no-site-retry.log。

首次严格模式全套测试因新增测试中的 `\|` 非法转义导致模块导入失败，已改为原始字符串；保留 final-tests.log，复测结果以 final-tests-retry.log 为准。

覆盖实际 Python 三模型（72/72/48 条）、混合 Stata/Python 来源、HC1/传统非聚类标准误、控制变量缺失损失、同 N 不同样本键、因变量比例与百分比分表、零值/未知/未纳入区分、精确 p 值边界、文件与状态篡改、重开和依赖失效。Python-only 测试禁止导入 Stata 引擎。

本地归档和普通 clone 测试各自从导出的使用文件树加载代码，利用实际冻结运行生成比较和 Word 并重新打开；同时核对运行树字节、入口和相对链接。使用当前安装的固定版本依赖，没有宣称在全新虚拟环境重新下载依赖。对外发布后的 GitHub clone/ZIP 下载核验仍待发布授权。

## 实际 Word 页面验收

渲染使用宿主 documents Skill 的打包 Python、LibreOffice 和 render_docx.py；产品无这些绝对路径依赖。首次渲染中文缺字，定位为字体配置问题，使用临时 FONTCONFIG_FILE 映射到本机 Songti SC 后重新渲染。随后修复默认标题边线、字体主题覆盖、宽表空白封面及表注分页问题，失败和中间材料仍保留。

最终打开全部 PNG 查看中文、对齐、裁切、表头和跨页。三列/六列/八列使用真实合成模型结果；长表为专门构造的 38 行版式压力样例，不能作为统计结果。final-report 为真实基准、增加控制变量、限制年份三模型交付。

| 文件 | 页数 | 视觉结果 | DOCX SHA-256 |
| --- | --- | --- | --- |
| models-3.docx | 3 | 全部逐页查看，通过 | `823d482134b8ddbe92e0bd39d9e341af22a06e9ca6e1d3a8e5688ff92d548374` |
| models-6.docx | 4 | 全部逐页查看，通过 | `da1598d0c5c7701198a64bf889e67186031b57b3d4b7c4979dfcb2e05ca828e5` |
| models-8.docx | 6 | 全部逐页查看，通过 | `d5d3c251dda407ced94380b0069ead1a56e0ae5fd01aa575253b840bee3b8d46` |
| long-table.docx | 5 | 全部逐页查看，通过 | `31bd17a87980b09fede02a1e491cf8b63efcc4190a4d9a2e4b9b6e77827dd6d7` |
| final-report.docx | 3 | 全部逐页查看，通过 | `c883e9257a8c3b3b0553d410c649557b550bad9266828619a8fcbb48941fe779` |

实际交付示例在临时项目中登记为 final-word v2；三页 PDF/PNG 全部看完后登记 final-review v1，render_check/visual_check 均通过；重新打开并调用 read_document_review、resume_context 核对可用。原 Word 记录的视觉状态仍为 not_performed，视觉结论在独立 review 中，不改写统计结果状态。

证据根：`/private/tmp/econbiz-stage-c-acceptance/`。`visual-manifest.json` 保留 DOCX/PDF/逐页 PNG 的完整散列；`verified-3/6/8/long` 和 `final-report-v2-render` 是本次查看的页面。`final-delivery.json` 与 `final-review.json` 记录实际版本。临时证据可能被系统清理，本文件保留验收范围及散列，不把临时路径当永久下载地址。

## Codex 宿主与新会话

在独立临时使用包中，通过公开入口和手册完成自然语言任务：读取三次真实运行、保存变量口径笔记、比较、Word 和接续笔记，没有为出表新增估计。另一个没有前次对话内容的只读会话正确恢复角色、72/72/48 样本及 24 条年份剔除，并明确 Word 尚未做视觉验收。输出日志分别为 host-events-retry.jsonl、host-final.txt、resume-events.jsonl、resume-final.txt。

首次 CLI 初始化被运行目录权限阻挡，重试后完成；该失败保留在 host-stderr.txt。宿主会话使用当时的实现快照；此后增加了严格段落检查、版式调整及审查修复。最终代码另由全套测试和父任务实际交付/重开验收覆盖，不把早期宿主会话描述为最终代码逐字节复验。Claude Code 宿主与跨宿主接续仍未实测。

## 审查发现与修复

完成只读代码审查，并用失败测试复现两项问题：非聚类模型的空聚类字段导致 Word 核对失败；接续仅检查外层状态而误把被改写系数的比较和 Word 标为有效。已分别规范空字段和接入严格读取器，并增加回归测试；独立审查者复跑两项测试通过，复查无新的重要问题。此前还通过测试修复了额外插入段落未被拒绝的问题。

## 实施说明与边界

- 首批 review 要求 PDF 与全部 PNG，而非可选 PDF，以实际 PDF 页数校验完整性；视觉观察仍是调用者声明，不认证观察者身份或渲染像素对应关系。
- Agent 解释附自有来源的研究笔记。程序核对实际表格数值及笔记是否忠实进入文档，不自动认证任意解释文字中的数值推导、测量定义或因果主张。Agent 必须在保存解释前按运行参数来源核对。
- 主估计不会因出表重新执行；严格读取会重算独立参考数值，因此需要分析依赖。无可选依赖的基础项目仍可读，未检查的交付不会宣称当前有效。
- 顺序实施后集中提交功能与验收，不按计划每一小任务单独提交。保留已有开发分支，不执行对外发布或合并到 main。


## 后续授权发布与公网复验（2026-09-16）

用户明确要求更新 main 与默认 ZIP 后，从开发分支 1f1f6dd 的 git archive 导出使用文件树，覆盖临时 main checkout 并正常提交、推送，没有合并开发测试或重写历史。中英文 README 同步为已发布状态。

- main 提交：`81b5ebb5e4a60b09739fddd9f61ff9529f3226c4`，版本 0.3.0a1。
- 实际无分支参数重新 clone GitHub，默认分支确认为 main；实际下载默认 main.zip。
- clone 与 ZIP 内的 74 个使用文件均与发布源逐字节一致，Markdown 相对链接有效。
- 两份下载均从各自目录导入代码，使用临时合成项目的真实三模型运行完成比较、Word 导出及重新打开，内容检查通过。
- 下载 ZIP SHA-256：`27bb55c6037fa91ad7c05b95f89eb89581c8b641e6f7c5f0ceea1f21db1ff2da`。
- 临时原始证据：`/private/tmp/econbiz-release-AaYuSi/verification.json`、`public-main.zip`、`public-clone/`、`download/`。新合成项目位于同一临时目录，未触及个人研究。

此发布复验覆盖实际分发及基本运行；统计和视觉验收沿用上文对应代码的已完成检查，不宣称再次执行全部统计测试或重复逐页验收。
