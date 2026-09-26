# 经管研究 Copilot 产品介绍页

静态中文网站，基于项目 0.3.0a2 的 README 和研究手册整理。设计参考 Ai4Scholar 的产品介绍结构，配图来自项目真实生成的合成数据示例。当前采用午夜蓝黑背景、蓝紫光晕与简洁细边框。

深色视觉参考 [Dark.Design](https://www.dark.design/)，早期交互灵感参考 [React Bits](https://reactbits.dev/) 和 [21st.dev](https://21st.dev/)。2026-09-26 根据用户提供的[前端库教程](https://vupyskvyxk.feishu.cn/wiki/IouWw3ihmihAsXkNILdc6DZ2nhc)，使用 Three.js 增加首屏研究网络，使用 Apache ECharts 增加可点选的系数区间图，并加入六阶段研究流程与示例问题联动。保持静态网站，不需要前端框架或构建服务。

研究路线和分析结果的预览参考 Codex 与 macOS 的简洁窗口、侧栏和信息层级，以实际报告内容重新排版。它们是报告展示版，不是独立桌面应用；保留原始 HTML 报告入口。分析结果中的系数区间图对应原报告的点估计和 95% 置信区间，数据均为合成示例。

## 查看

在线访问：[经管研究 Copilot](https://econbiz-research-copilot.pages.dev/)。

完整动效请通过 HTTP 预览；直接打开 `index.html` 时，浏览器可能限制 Three.js 模块加载，页面会保留静态背景。从仓库根目录启动本地预览：

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory website
```

浏览器访问 `http://127.0.0.1:8765/`。无安装或构建步骤，无远程字体、跟踪脚本、账户或后台服务依赖；新增库固定版本保存在 `vendor/`，页面运行时不请求外部 CDN。

## 文件

- `index.html`：内容、导航、预览、使用说明与常见问题。
- `styles.css`：桌面和手机排版。
- `theme.css`：深色主题、背景光晕、文字渐变、滚动渐入和卡片视觉效果。
- `showcase.css`：报告预览的简洁边框、完整图片比例与响应式卡片布局。
- `app.js`：预览切换、图片放大、手机导航与提示词复制。
- `motion.js`：滚动进度、导航定位与鼠标聚光交互。
- `interactions.js` / `interactions.css`：六阶段探索、示例问题联动和 ECharts 系数区间图。
- `research-network.js`：Three.js 首屏研究网络，响应鼠标位置与视口变化。
- `vendor/`：固定版本的 Three.js、ECharts、许可证、来源和 SHA-256。
- `assets/`：两张 `*-macos.jpg` 报告展示版截图、原始 HTML 报告截图和实际 PDF 页面。
- `previews/`：展示版 HTML 与共用样式；两张新版图片由浏览器在 960 × 600 视口直接截取。
- `examples/`：完整可打开的 HTML 报告和 PDF 示例。

更新内容时以当前 README、实际功能和有效手册为准。示例为合成数据，不属于真实企业研究；不得把文件结构示意写成已实现的独立研究网页应用。图片来源与哈希保存在仓库的 `docs/website-assets-20260918.json`。

按用户要求，已移除页面动效开关和减少动态效果功能，默认展示动效。手机不启用鼠标倾斜效果；背景在离开视口或页面切至后台后停止绘制，返回时继续。无 WebGL 时保留 CSS 背景。ECharts 在图表接近视口时加载，加载失败时保留数值表；未启用 JavaScript 时仍能阅读六个研究阶段、数值表与原始报告链接。

交互图表仅展示 `examples/analysis-report.html` 的既有合成结果；选择变量改变高亮与说明，不改变估计值、样本或模型。图表使用固定的横轴范围，便于对比两项估计。研究阶段中的文件结构和文献流程明确标为示意，报告图片保持合成示例标识。

## 自动发布

使用 Cloudflare Pages 的 GitHub 集成发布。将网页修改推送至 GitHub 的 `main` 分支后，Cloudflare 自动部署 `website/`。生产分支为 `main`，框架选择 None，构建命令留空，输出目录为 `website`。

构建监听路径为 `website/*`（包含子目录）；日常修改网页以外的文件不会触发重新部署。

无需安装依赖、填写构建命令或另存访问密钥。发布范围仅为 `website/`；项目其余目录不会上传到网页站点。上线状态以 Cloudflare Pages 的实际部署结果为准。

网站文案、主题和交互在本目录修改。维护分支的更新需要同步到 `main` 才会正式上线；同步时只带入网页与部署配置，保持研究工具使用版与开发材料的原有边界。
