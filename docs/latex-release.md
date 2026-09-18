# LaTeX 与 PDF 使用版发布检查

日期：2026-09-18；版本：`0.3.0a2`。用户在功能实现与验收后明确要求“更新”，本次同步开发分支、默认 `main` 与公开 ZIP。

## 发布内容与提交

- 发布源：`45e47198e64a69f8619dafd039f3b6940c650075`。
- 使用版 main：`28b5c84182c23fded55895400f1a1d22bfdecad0`，从 `81b5ebb` 正常追加提交。
- main 文件树由开发分支 `git archive` 导出，在隔离的临时 main checkout 中更新；没有整体合并开发分支、强制推送或重写历史。
- 本次新增 6 个使用文件，没有删除已有使用文件。默认 clone 与 ZIP 均为 **80 个文件**，保留两套 Skills、入口、模板、工具和使用手册；不包含开发测试、脚本、实施记录或研究数据。
- 中英文 README 同步说明 LaTeX 导出、PDF 编译及 XeLaTeX 环境要求，软件包与模块版本一致为 `0.3.0a2`。
- 开发材料保留在 `codex/framework-foundation`；本发布记录及验收文档更新被归档规则排除，不改变公开使用文件字节。

## 发布前检查

完整功能、统计和视觉验收见 [LaTeX 验收记录](latex-validation.md)：289 项测试，以及最终 11 页 PDF 的实际观察。版本号和 README 更新后，再运行分发、LaTeX 分发与 Skills 包检查，**10 项通过，10.886 秒，无跳过**，其中包含真实 XeLaTeX 编译。Skills 同步和差异检查通过。

## 公开下载后的验收

从 GitHub 重新普通 clone（不指定分支），另从 README 的 [main ZIP 链接](https://github.com/jyq0221/econbiz-research-copilot/archive/refs/heads/main.zip) 实际下载并解压：

- 默认 clone 分支为 main；clone 的提交与 ZIP 内提交标识均为上述 `28b5c84`。
- clone、ZIP 与发布源的 80 个文件路径及字节完全一致；全部本地 Markdown 链接可解析，两套 Skills 内容一致。
- 两份下载内容分别在独立临时合成项目中实际运行两个 Python 固定效应模型，每个使用 72 个观测，执行与独立数值复核均通过。运行前及结束时断言全部 econbiz 模块来自相应下载目录。测试夹具来自开发测试，仅用于生成合成输入与方案，不作为用户材料发布。
- 每份下载内容均实际生成单模型英文内置标签和双模型中文 LaTeX，附保存的结果说明与带来源公式；源码实际内容核对通过。
- 两份下载内容共原生编译 4 个 PDF，每份 2 页，编译警告均为空；严格读取、PDF 结构和散列核对通过。
- 重新打开两个项目后，四类源码/PDF 交付记录均可用，来源与版本绑定有效。
- 此次公网复验未重复逐页观察，4 个新 PDF 的 `visual_check` 保持 `not_performed`；版式证据沿用对应代码在实现验收中实际观察的 11 页，不把原生编译等同视觉通过。

实际下载 ZIP SHA-256：`f593c5c814cdf696ac905def78112be2b6393deb4b8899f6a9820d76e0dd5b5e`。

临时证据目录：`/private/tmp/econbiz-latex-release-emge5out/`。`verification.json` 保存提交、下载散列和实际流程结果；`public-clone/`、`download/` 为公网获取内容，`clone-check/`、`zip-check/` 为独立合成项目。临时目录清理后这些本机证据可能不再保留。

使用现有已验收的 Python 依赖和便携 XeLaTeX；本次没有声称在全新机器安装依赖、重新测试所有 Agent 宿主，或重复进行完整统计测试。既有测试数据 Release 附件未改变。
