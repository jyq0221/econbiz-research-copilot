@AGENTS.md

在 Claude Code 中，从本工具仓库根读取项目入口，专项 Skills 使用 [.claude/skills/](.claude/skills/) 下的同名副本，共用 [研究手册](docs/research-handbook/principles.md)。
普通文件副本随仓库发布，使用者无需全局安装或运行同步脚本。未自动发现时按入口直接读取对应 SKILL.md。实际平台验证状态见 [验收记录](docs/agent-entry-validation.md)。
