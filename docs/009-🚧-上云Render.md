# 009 · 上云（Render）

> **状态**：🚧 —— Docker / 邀请码 / 备份恢复已落地；等用户在 Render 点完创建服务并迁真库。
> **前置**：云是唯一正库，见 [005](005-🚧-社区版与多租户.md)。小主机 `data/` 在切换日前仍是真库存。切换日前的本机防毁账见 [010](010-🚧-防毁账与本地耐久.md)，不要和本文件的 Render 步骤混在一轮。

# ✅ 已完成：上云包装与邀请码

`Dockerfile` 构建前端并跑 FastAPI。`render.yaml` 挂 `/data` 磁盘。设了 `COFFEEBAR_INVITE_CODE` 时，注册必须带邀请码。`POST /api/ops/restore` 用 `X-Restore-Key` 接收 `backup.bat` 的 zip。

小主机不配邀请码，登录页不变。

# 🚧 进行中：在 Render 上点出来（给不会的人）

真库存必须挂持久盘。Render **免费 Web 没有持久盘**，请用 **Starter**（每月几美元）+ **2 GB Disk**。

## 你先准备

1. 浏览器打开 [https://render.com](https://render.com)，点 **Get Started**，选 **GitHub**，用 `dpmoehre` 登录。
2. 授权 Render 能看到仓库 `dpmoehre/coffeebar`。
3. 自己在本子上写下两串，**不要发到聊天里**：
   - 邀请码（以后注册用，例如一串无意义字母）
   - 恢复密钥（上传备份 zip 用，另写一串）
4. 小主机上双击 `scripts/backup.bat`，确认 `%USERPROFILE%\coffeebar-backup` 里有最新 zip。**然后关掉 `start.bat`。**

## 创建网站（第一次）

1. Render 首页点 **New +** → **Blueprint**。
2. 选仓库 `coffeebar`，分支 `main`。
3. 它会读 `render.yaml`。名称保持 `coffeebar`。
4. 填三个要你手填的变量（页面上会标 `sync: false`）：
   - `COFFEEBAR_PUBLIC_URL`：先填 `https://coffeebar.onrender.com`，创建后如果实际网址不一样，再改成仪表盘上的真实地址。
   - `COFFEEBAR_INVITE_CODE`：你本子上的邀请码。
   - `COFFEEBAR_RESTORE_KEY`：你本子上的恢复密钥。
5. 确认 Disk 挂在 `/data`，大小 2 GB。
6. 点创建，等第一轮 Deploy 变绿（第一次编 Docker 可能 5–10 分钟）。
7. 打开 Render 给的网址，应看到登录页。不要先让别人打开。

如果不用 Blueprint： **New +** → **Web Service** → 连 `coffeebar` → Runtime 选 **Docker** → Instance **Starter** → 加 Disk ` /data ` 2 GB → 环境变量按上面填。

## 把真库传上去

在你的 Mac 终端（把两处换成真实值）：

```bash
curl -F "file=@/那份备份.zip" \
  -H "X-Restore-Key: 你的恢复密钥" \
  https://你的站点.onrender.com/api/ops/restore
```

回到 Render → 这个服务 → **Manual Deploy** → **Deploy latest commit**（或 Restart）。等变绿。

## 你第一个注册

打开云网址 → 注册 → 填**邀请码**和你的邮箱密码（至少 8 位）。  
这个号会接手迁上去的豆和酒。确认豆还在、照片能打开。

之后小主机**不要再开** `start.bat`。日常只开云网址。推 `main` 会自动重新部署，磁盘上的账本还在。

# ⌛️ 未完成：用户点完 Render 并迁库验收
