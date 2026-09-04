@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

if not exist "web\dist\index.html" (
  echo.
  echo   前端还没构建。先双击 install.bat。
  echo.
  pause
  exit /b 1
)

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  if not defined LANIP set "LANIP=%%a"
)
set "LANIP=%LANIP: =%"

echo.
echo   coffeebar 跑起来了
echo   ========================================
echo   这台机器    http://localhost:8000
if defined LANIP echo   同一个网    http://%LANIP%:8000
echo.
echo   关掉这个窗口就停。
echo.

start "" http://localhost:8000
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
