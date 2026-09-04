# coffeebar

公司咖啡吧里的个人手冲 / 调酒工具。远程：[github.com/dpmoehre/coffeebar](https://github.com/dpmoehre/coffeebar)。

**不是点单点菜系统。** 第一期做豆子档案：豆卡（产地、风味、克重）、消耗流水、带 SVG 动画的冲煮指导、拍照上传。运行在一台 Windows 11 小主机上，公司内网访问，必要时临时走 cpolar。

小主机、手机和其他电脑**功能相同**，只换页面布局。全站统一现代吧台 UI 与动效。同一条豆卡同时只允许一个设备在改（写锁），避免多端互踩。

架构与运行环境见 [docs/002-🚧-豆子档案与小主机架构.md](docs/002-🚧-豆子档案与小主机架构.md)。应用代码尚未落地。

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
