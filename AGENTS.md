# AGENTS.md — coffeebar

本仓库对 **所有 AI Agent**（Codex、Cursor、Claude Code 及其他兼容工具）的约定，**正文统一维护在 [CLAUDE.md](CLAUDE.md)**。

> 本文件不重复规则内容，只作引用入口，避免双份漂移。**请先完整阅读 [CLAUDE.md](CLAUDE.md) 再开始工作。**

## 规则要点索引（详见 CLAUDE.md 对应章节）

- **项目定位 / 架构概览** — coffeebar 绿场仓库。真库存耐久待修见 [docs/010-⌛️](docs/010-⌛️-防毁账与本地耐久.md)；细则仍以 CLAUDE.md 为准。
- **环境与工具** — 技术栈未定时不提前锁定；Python 用 uv，前端用 npm；密钥与本机 Temp 不入库。
- **Git 与版本控制** — 每完成一条队列任务即 `git add`+`commit`+`push` 到 `origin`（与 [`.cursor/rules/queued-task-then-push.mdc`](.cursor/rules/queued-task-then-push.mdc) 一致）；用户说暂不推送则尊重。
- **任务事项推进与跟踪** — 任务看板写在 **`docs/NNN-状态-主题.md`**，子任务用 H1 状态标题（✅/🚧/⌛️）；`todo.md` 只记按日期**倒序**的精炼索引；`README.md` 只写功能/使用说明；用户能看见的改动白话写入更新页（详见 CLAUDE.md）。交给用户时给手工测试集合，测了/没测记在 [docs/006-🚧-手工验收.md](docs/006-🚧-手工验收.md)。
- **文件命名** — 普通 Markdown 用 `YYYY-MM-DD-` 前缀；任务文档用 `NNN-状态-主题.md`。

以上均以 **[CLAUDE.md](CLAUDE.md)** 为准；如有冲突，以 CLAUDE.md 为唯一正文。
