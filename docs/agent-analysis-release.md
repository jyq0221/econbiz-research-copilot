# 自动分析与双引擎使用版发布检查

日期：2026-09-16；版本：`0.2.0a3`。用户在开发分支复核和推送后明确要求“全部更新”，本次已同步默认 `main` 与公开 ZIP。

## 发布内容与提交

- 导出源：`df26d96ea8ecc4314aaf38ccad484caa789f70f1`；包含自动项目脚本、常见处理、可选 Stata 及推送前复核修复。
- 使用版 main：`b9567fbfe0ffca6ae4932683296ca503530af274`，从旧版 `a90adc2` 正常追加提交并推送。
- 开发材料继续保存在 `codex/framework-foundation`；本次发布记录只更新开发文档，不改变已发布的使用文件字节。
- [当前使用包](https://github.com/jyq0221/econbiz-research-copilot/archive/refs/heads/main.zip) 实下载 SHA-256：`c29ea0f30411d75f88b73652c0daf22335d68ca48a6c3d99eb2bf78bd61bce98`。

main 使用开发分支的归档导出内容；保留既有 Git 历史。本次增加 11 个使用文件，没有删除原有使用文件。默认 clone 和 ZIP 均为 **67 个文件**，包含五个 Skills 的两套普通文件、项目入口、软件包配置、工具代码、五份使用手册及反馈模板。

## 发布前检查

| 检查 | 实际结果 |
| --- | --- |
| 全套测试，显式启用真实 Stata | 244 项通过、0 跳过，113.864 秒 |
| Skills 源与副本 | 同步检查通过 |
| 差异检查 | 通过，无空白错误 |
| 临时 main 导出树 | 67 个文件逐字节匹配导出源；本地 Markdown 链接及两套入口通过 |
| 本地使用版流程 | Python、Stata 均跑通 72 行合成数据的处理、正式回归、项目脚本、报告、重跑与恢复 |

四处复核问题、五项新增回归测试及独立审查结果见 [实现验收记录](agent-analysis-validation.md)。没有增加新研究设定或变更测试数据附件。

## 公开下载后的验收

从公开仓库地址重新默认 `git clone`，未指定分支或稀疏检出；另从 README 的 main ZIP 链接实际下载并解压：

- clone 的当前分支为 main，提交与上文一致；ZIP 内提交标识也一致。
- clone、ZIP 与本地导出内容的 67 个文件路径和字节完全一致。
- 两套 Skills 一致，全部本地 Markdown 链接可解析；不含 tests、examples、scripts、内部实施文档或研究数据文件。
- 分别从 clone 和 ZIP 运行 Python、Stata，共四次独立流程；每次都断言实际导入来自对应下载目录。
- 每次实际完成按年 1%/99% 缩尾、log1p、Python 独立处理复核；来源登记后运行企业/年度固定效应并通过独立统计复核。
- 每次另实际执行对应语言的完整 OLS 项目脚本，状态保持 `completed/pending`，没有把退出成功当成统计核验通过。
- 四种报告格式（HTML、Markdown、CSV、JSON）均保存；冻结正式运行重跑结果一致；重新打开项目后，来源、盘点、方案、运行文件与报告均可核对。
- 两次 Python 流程均未导入 Stata 运行模块；无 Stata 用户仍可使用完整 Python 路径。

本机临时证据目录：`/private/tmp/econbiz-a3-release-bs7hau4h/`。`published.json` 保存 main 提交和 ZIP 散列，四个 `clone-python`、`clone-stata`、`zip-python`、`zip-stata` 目录保存实际运行与 `summary.json`；不作为用户研究材料发布。

## 当前能力范围

宿主 Agent 结合研究问题与数据推荐方法，在已获授权内处理数据、编写和运行 Python/Stata 项目脚本、修复技术错误并保存证据。默认 Python；本次原生 Stata 实测范围仍是 macOS arm64 / Stata 19。

常见处理和内置描述统计/固定效应有独立参考。其他项目方法按实际检查范围交付；DID、IV、权重和多维聚类的通用独立统计核验器仍须逐项扩展。实际运行、数值复核和因果识别分别判断。
