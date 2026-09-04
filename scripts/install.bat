@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo.
echo   coffeebar 安装
echo   ========================================
echo.

where uv >nul 2>nul
if errorlevel 1 (
  echo   [1/3] 装 uv...
  powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
) else (
  echo   [1/3] uv 已经有了
)

echo   [2/3] 装后端依赖（第一次会下 Python，慢一点）...
uv sync
if errorlevel 1 goto fail

where npm >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [3/3] 没找到 npm。去 https://nodejs.org 装 Node LTS，装完再跑一次这个脚本。
  goto fail
)

echo   [3/3] 装前端依赖并构建...
cd web
call npm install
if errorlevel 1 goto fail
call npm run build
if errorlevel 1 goto fail
cd ..

echo.
echo   装好了。双击 start.bat 开始用。
echo.
pause
exit /b 0

:fail
echo.
echo   没装成。把上面的红字截图发出来。
echo.
pause
exit /b 1
