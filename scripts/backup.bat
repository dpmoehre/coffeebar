@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

if not exist "data\coffeebar.db" (
  echo   还没有数据可以备份。
  pause
  exit /b 1
)

for /f %%i in ('powershell -c "Get-Date -Format yyyy-MM-dd-HHmm"') do set STAMP=%%i
set "OUT=%USERPROFILE%\coffeebar-backup"
if not exist "%OUT%" mkdir "%OUT%"

echo   正在备份到 %OUT%\coffeebar-%STAMP%.zip
echo   （豆卡照片一起打包，可能要等一会）

rem 用 SQLite 的在线备份，服务开着也能安全导出
uv run python -c "import sqlite3,sys; s=sqlite3.connect('data/coffeebar.db'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close(); s.close()" "%TEMP%\coffeebar-snapshot.db"
if errorlevel 1 goto fail

powershell -c "$t='%TEMP%\coffeebar-pack'; Remove-Item $t -Recurse -Force -EA 0; New-Item $t -ItemType Directory | Out-Null; Copy-Item '%TEMP%\coffeebar-snapshot.db' \"$t\coffeebar.db\"; if (Test-Path 'data\photos') { Copy-Item 'data\photos' $t -Recurse }; Compress-Archive -Path \"$t\*\" -DestinationPath '%OUT%\coffeebar-%STAMP%.zip' -Force; Remove-Item $t -Recurse -Force"
if errorlevel 1 goto fail

del "%TEMP%\coffeebar-snapshot.db" >nul 2>nul
echo.
echo   备份好了：%OUT%\coffeebar-%STAMP%.zip
echo.
pause
exit /b 0

:fail
echo   备份失败。
pause
exit /b 1
