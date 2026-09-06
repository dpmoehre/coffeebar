@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
uv run python -m app.backup pack
if errorlevel 1 goto fail
echo.
pause
exit /b 0
:fail
echo   备份失败。
pause
exit /b 1
