@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv\Scripts\coffeebar-mcp.exe" (
  ".venv\Scripts\coffeebar-mcp.exe"
  exit /b %ERRORLEVEL%
)
if exist "%USERPROFILE%\.local\bin\uv.exe" (
  "%USERPROFILE%\.local\bin\uv.exe" run coffeebar-mcp
  exit /b %ERRORLEVEL%
)
echo coffeebar-mcp: 先跑 scripts\install.bat 1>&2
exit /b 1
