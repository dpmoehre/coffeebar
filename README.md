# coffeebar

绿场仓库。远程：[github.com/dpmoehre/coffeebar](https://github.com/dpmoehre/coffeebar)。

当前已落地 **Agent 协作框架**（工作牌 / AGENTS / CLAUDE / todo）。产品功能与技术栈待 `_Doc/` 需求补齐后写入本页。

---

## 目录

| 路径 | 说明 |
| ---- | ---- |
| [CLAUDE.md](CLAUDE.md) | Agent 规则唯一正文（Claude Code / Cursor / Codex 共用） |
| [AGENTS.md](AGENTS.md) | 引用入口，不重复规则正文 |
| [todo.md](todo.md) | 按日期倒序的精炼变更/验收索引 |
| [docs/](docs/) | 任务看板（`NNN-状态-主题.md`） |
| [_Doc/](_Doc/) | 人工需求、纪要、架构、配图 |
| [.cursor/rules/](.cursor/rules/) | Cursor 工作牌（始终生效的仓库规则） |

---

## 给 Agent 的入口

1. 先读 [CLAUDE.md](CLAUDE.md)。
2. 查 [todo.md](todo.md) 与 `docs/` 文件名，决定复用还是新建看板。
3. 子任务用 H1 状态标题（✅ / 🚧 / ⌛️）；收尾只在 `todo.md` 顶部追加索引，并更新 README 的功能说明（如有）。

规则细节以 CLAUDE.md 为准，本页不复制。
