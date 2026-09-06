@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
if "%~1"=="" (
  echo   用法：restore.bat 备份.zip [--dest 目录] [--force]
  pause
  exit /b 1
)
uv run python -m app.backup restore %*
if errorlevel 1 goto fail
echo.
pause
exit /b 0
:fail
echo   还原失败。
pause
exit /b 1
