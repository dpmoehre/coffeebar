# 定时备份（本机配置，不入库口令）

默认每天一份。先设异地目录，再挂计划任务。

```bat
setx COFFEEBAR_BACKUP_DIR D:\coffeebar-backup
```

```bash
export COFFEEBAR_BACKUP_DIR=/Volumes/NAS/coffeebar-backup
```

## Windows 任务计划程序

1. 打开「任务计划程序」→ 创建基本任务。
2. 触发器：每天，吧台开门前（例如 09:00）。
3. 操作：启动程序 `…\coffeebar\scripts\backup.bat`（或 `uv` 工作目录指到仓库根，参数 `-m app.backup pack`）。
4. 用本机已登录的用户跑，才能读到 `setx` 的环境变量。设完开一个新的 cmd 试一次。

## Mac launchd

`~/Library/LaunchAgents/local.coffeebar.backup.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>local.coffeebar.backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/绝对路径/coffeebar/scripts/backup.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>9</key><key>Minute</key><integer>0</integer></dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>COFFEEBAR_BACKUP_DIR</key>
    <string>/Volumes/NAS/coffeebar-backup</string>
  </dict>
</dict>
</plist>
```

`launchctl load ~/Library/LaunchAgents/local.coffeebar.backup.plist`

## cron

`0 9 * * * COFFEEBAR_BACKUP_DIR=/mnt/nas/coffeebar-backup /path/to/coffeebar/scripts/backup.sh >> ~/coffeebar-backup.log 2>&1`
