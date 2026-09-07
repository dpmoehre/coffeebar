@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if not exist "web\dist\index.html" (
  echo host-app: 前端还没构建。先跑 scripts\host-update.ps1
  exit /b 1
)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
