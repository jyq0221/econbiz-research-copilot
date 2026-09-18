# Economics & Business Research Copilot

[简体中文](README.md) | **English**

**Clarify your research choices and pick up where you left off.**

You have a research topic but are unsure which data to collect. You have read several papers but still need to choose a measure. Your supervisor has suggested a change, and you want to keep track of what changed and why.

Research Copilot helps you develop questions, compare designs, check evidence, and save your discussions and files so you can continue later. Beginners can start with an idea; experienced researchers can use it to spend less time finding materials, checking versions, and reconstructing earlier decisions.

> 🌱 **An early release for research preparation and Python/Stata analysis.** Codex is currently the primary tested environment. You do not need a complete hypothesis or a list of skill names to get started.

[Get started](#get-started) · [Try a small task](#try-a-small-task) · [Share feedback](#share-feedback)

## What can it help with?

| You might be thinking… | What we can work through |
| --- | --- |
| “I want to study firm digitalization, but the topic is too broad.” | Turn the interest into questions worth comparing, with the evidence and data each would need. |
| “These papers study risk but use different measures.” | Compare the definitions, methods, and results actually available, then assess their fit for your question. |
| “I want to check my data before merging.” | Inspect firm-year CSV files for duplicate keys, missing-value markers, and unusual numeric values, and save a report. |
| “My supervisor says this measure is unsuitable.” | Compare alternatives, their meaning, data requirements, and sample costs while keeping the original design and reasons for revision. |
| “My regression is not significant. Was the work wasted?” | Discuss direction, magnitude, and precision, distinguishing insufficient evidence from evidence of no relationship. |
| “Where did I leave off?” | Recover the question, materials, open issues, and next step from saved research records. |

You should be able to understand **why a suggestion is made, what supports it, and what still needs checking**.

## Keep your attention on research decisions

A long-running project also brings practical questions: Which version produced this table? Why did we change that measure? What did we agree to check next?

Copilot can help you:

- **Organize materials:** Keep literature, data, designs, discussions, evidence, and open tasks together by project.
- **Trace revisions:** Preserve earlier versions and reasons for changes, and identify downstream materials that need another check.
- **Resume interrupted work:** Review current records, unresolved questions, and next steps.
- **Interpret existing results:** Discuss estimates and uncertainty in light of their sources and specifications, and record outstanding verification tasks.

Methods and conclusions remain research judgments. The assistant can organize evidence and execute supported Python or Stata regressions under an approved plan, retaining outputs that can be checked. The supported scope is described below.

For example:

> I already have a research plan and preliminary results. Read the project materials I specify, summarize the current question, main designs, reasons for revisions, and open tasks. Distinguish verified facts from my descriptions, then prioritize next steps. Keep the existing research specification for now.

## Get started

### What do you need?

**An AI agent environment that can read and edit project files, call tools, and execute code.** Examples include Codex, Claude Code, or an agent harness connected to a model such as DeepSeek. Configure your model service and give the environment access to the project directory and the programs it needs.

This repository supplies research workflows, skills, and analysis tools. Your agent environment supplies the assistant and model service. Actual host testing currently focuses on Codex. Claude Code entry files are provided; other environments need their own compatibility checks.

### 1. Download the project

Choose **Code → Download ZIP** above, or [download the user package](https://github.com/jyq0221/econbiz-research-copilot/archive/refs/heads/main.zip), then extract it.

You can also clone the default `main` branch. **Both the default clone and ZIP contain the user version**, including entry files, templates, tools, and handbooks. Synthetic datasets, development tests, and internal implementation records are distributed separately.

No data of your own yet? [Download the optional trial dataset](https://github.com/jyq0221/econbiz-research-copilot/releases/download/trial-data-v1/econbiz-trial-data-v1.zip). It contains a complete panel, a deliberately problematic practice file, field descriptions, and an answer guide. Its documentation is currently in Chinese.

### 2. Open the whole folder in your agent environment

Open the folder containing this README, `AGENTS.md`, and `econbiz`. Start a conversation and ask the assistant to read the project entry instructions.

You can discuss a research idea right away. CSV checks, saving projects, and file recovery require **Python 3.9 or later**. If you are unsure about your setup, say:

> Check whether this project is ready to use on my computer. Explain what I can start doing in plain language.

### 3. Describe your question

There is no long intake form. Point the assistant to your materials, or start with one of the examples below.

If the assistant does not follow the project workflow, add: “Read this project's AGENTS.md and use the research entry skill to help me get started.”

**Delivery language follows your request.** Replies and final deliverables should use the language of your current request unless you explicitly ask for another language. For example, you can discuss a project in Chinese and request an English report. An English source paper or a Chinese README does not by itself determine your output language. Handbooks and built-in report templates are currently mainly in Chinese; this English README does not mean every generated template has been localized.

## Try a small task

### 💡 Start with an idea

> I want to study firm digitalization and operating risk, but I do not have data yet. Break this into two or three research questions and explain what data each would need. Leave uncertain points open for verification. Do not create a project yet.

**Look for:** A clearer definition of risk, meaningful differences between the questions, and a useful next step for finding evidence.

### 🔎 Check your own data

> Inspect the firm-year CSV I provide. First identify the firm and year columns, then check duplicates, missing values, and unusual numbers. Ask about unclear field meanings; do not fill missing values with zero or delete records automatically. Save the inventory and discussion in research-projects/first-try and preserve the raw data.

**Look for:** Specific records, an explanation of why they matter, and a report and progress record you can open.

If you use the [trial dataset](https://github.com/jyq0221/econbiz-research-copilot/releases/download/trial-data-v1/econbiz-trial-data-v1.zip), read its instructions and point the assistant to `panel_with_issues.csv`. It should identify duplicate keys, missing-value markers, and unexplained text while retaining the original records. Then compare its findings with `核对答案.md` (the answer guide). All firms and values are synthetic and for practice only.

### 📚 Bring a paper

> Read the paper I provide. Explain how its authors define and measure the core concepts, then assess whether those choices could fit my question. Give the actual source for each claim, distinguish the authors' findings from your inferences, and do not invent content you cannot access.

**Look for:** Clear sources, an honest account of what was read, and a connection to your own question. Full-text access and web search depend on your agent environment and its available tools.

## Continue later without starting over

When you choose to save work, each study has its own folder, usually `research-projects/<project-id>/`:

| File or folder | Contents |
| --- | --- |
| `研究进展.md` | The current question, progress, and next step. Start here when returning. |
| `literature/` | Papers and evidence notes. |
| `data/` | Raw data, field descriptions, and derived materials. |
| `research/` | Plans, discussions, tasks, decisions, reports, and checkpoints. |

Earlier versions remain available when you revise an idea or measure. Continuity depends on records that were actually saved; ask the assistant to state what it saved after important discussions.

After the data task above, try a new conversation:

> Continue research-projects/first-try. Based on the saved materials, explain what we found, what remains unknown, and why the next step is worth taking.

Open the repository root when resuming. If different assistants take turns on the same study, finish one writer's work before another starts. Keep existing file paths and identifiers unchanged when switching languages.

## What is implemented?

**Research preparation, the first formal analysis tools, and model comparison and Word delivery are connected.** The workflow supports Excel/CSV input, descriptive statistics, fixed-effects regressions, independent numerical checks, result reports, versioning, and resumption. Python is the default; Stata is optional.

Version 0.3.0a1 adds ordered comparisons of checked models, actual sample comparisons, and editable Word tables with three horizontal rules. Reports include variable definitions, descriptive statistics for each model's sample, and source versions. File generation, numeric/text checks, and page-by-page visual review are recorded separately. See [model comparison and Word delivery](docs/research-handbook/result-delivery.md) (Chinese). These features are included in the default main branch and ZIP. The built-in Word template is currently Chinese.

### Can it actually run regressions?

**Yes, under an approved plan, using supported Python or Stata methods.** The initial built-in scope covers linear fixed-effects association models for firm-year panels, with firm/year fixed effects, conventional or HC1 standard errors, and one-way clustered standard errors. The assistant checks field mappings, filters, missing-data rules, and the environment before execution and verification.

| Stage | Current support |
| --- | --- |
| Before analysis | Read Excel/CSV, assess methods against the question, check measures and samples, and propose a short processing plan. |
| Data preparation | Winsorize, take logs, construct variables, and check merges under explicit rules, preserving original values and processing records. |
| Execution | Generate Python/Stata project code, freeze inputs and environment information, execute it, and fix technical errors. |
| Existing results | Save external tables and discuss them with their specifications and sources, clearly marking results that have not been reproduced. |
| Independent checks | Check common transformations and built-in estimates against independent implementations; record the actual checking scope for other methods. Successful execution alone is not verification. |
| Reports and reruns | Produce tables and explanations, retain all results, flag outdated outputs when data or plans change, and rerun under the newly approved version. |

**Describe your research question and let the assistant assess methods, prepare data, and write and execute Python or Stata code.** Common transformations include winsorization, logs, ratios, interactions, standardization, and lags based on actual time intervals. The assistant should give a short plan, continue within existing authorization, and deliver code, data, results, and checking records. See the [project analysis workflow](docs/research-handbook/project-analysis.md) (Chinese).

**Python can complete the supported analysis without Stata.** Built-in descriptive statistics and fixed-effects estimates have independent numerical checks; see the [formal analysis handbook](docs/research-handbook/analysis-execution.md) (Chinese). The tested native Stata configuration is macOS arm64 with Stata 19. For DID, IV, weights, and multi-way clustering, the assistant can assess the research basis and write project code; a general independent verification framework for those methods is not yet connected. Results distinguish “executed” from “independently checked.” Numerical agreement does not establish causality.

Try: **“Check my saved plan and data, run the approved Python regression using the agreed sample and specification, and provide the independent checking record and result report.”**

We preserve uncertainty, avoid treating non-disclosure as zero, retain earlier plans and results, and explain research revisions. Passing a check does not establish measurement validity, and finding significance is not the definition of progress.

<details>
<summary>Current validation scope</summary>

- The original 108 Phase A tests are retained. Phase B added real regressions, independent numerical comparisons, error injection, frozen-package reruns, and report checks. See the [project-analysis validation record](https://github.com/jyq0221/econbiz-research-copilot/blob/codex/framework-foundation/docs/agent-analysis-validation.md) (Chinese).
- Ten synthetic Codex scenarios and independent new-session resumption were tested, with timeouts, fixes, and retests recorded.
- Claude Code adapter files are provided; actual host testing and cross-host handoffs remain unverified.
- Real-user feedback is being sought. Learning outcomes for beginners have not yet been established.

See the [validation record](https://github.com/jyq0221/econbiz-research-copilot/blob/codex/framework-foundation/docs/agent-entry-validation.md) for evidence and outstanding conditions (Chinese).

</details>

## Share feedback

One small task is a good first trial. We especially want to know:

1. **What became clearer?** Did you better understand the question, measure, or next step?
2. **What was still confusing?** Was an explanation too technical or an action unclear?
3. **What did not work?** For example, missing outputs, lost context when resuming, or unsupported claims.

👉 [Submit trial feedback](https://github.com/jyq0221/econbiz-research-copilot/issues/new?template=trial-feedback.md), or share your experience with the person who invited you. Include what you asked, what the assistant did, and what you expected.

GitHub feedback is public. Describe sensitive issues without posting raw data or entire papers.

## Learn more

The following documentation is currently in Chinese:

- [Research principles](docs/research-handbook/principles.md): Evidence, measurement, and research decisions.
- [Validation record](https://github.com/jyq0221/econbiz-research-copilot/blob/codex/framework-foundation/docs/agent-entry-validation.md): What has been checked and what remains open.
- [Development guide](https://github.com/jyq0221/econbiz-research-copilot/blob/codex/framework-foundation/docs/development-guide.md): Interfaces, environments, and development practices.
- [Design and development standards](https://github.com/jyq0221/econbiz-research-copilot/blob/codex/framework-foundation/docs/design-and-development-standard.md): Project goals and the broader analysis roadmap.

Source maintenance, development tests, and implementation records live on the [development branch](https://github.com/jyq0221/econbiz-research-copilot/tree/codex/framework-foundation).

## LaTeX and PDF result delivery

Ask the agent to export existing regression results, explanations and model equations to LaTeX and PDF. Single-model and multi-model tables retain checked values and source versions. PDF generation requires XeLaTeX; compilation and page-by-page visual review have separate statuses. See the [LaTeX delivery guide](docs/research-handbook/latex-delivery.md) (Chinese) for supported inputs and setup.
