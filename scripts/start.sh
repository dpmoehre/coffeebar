#!/usr/bin/env bash
# Mac / Linux：托管已构建的前端 + API。对标 scripts/start.bat。
# 改前端源码要热更新时用：bash scripts/dev.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f web/dist/index.html ]]; then
  echo
  echo "  前端还没构建。先跑：  bash scripts/install.sh"
  echo
  exit 1
fi

LAN=""
if command -v ipconfig >/dev/null 2>&1; then
  for iface in en0 en1; do
    if ip=$(ipconfig getifaddr "$iface" 2>/dev/null); then
      LAN=$ip
      break
    fi
  done
elif command -v hostname >/dev/null 2>&1; then
  LAN=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

echo
echo "  coffeebar 跑起来了"
echo "  ========================================"
echo "  这台机器    http://localhost:8000"
if [[ -n "${LAN}" ]]; then
  echo "  同一个网    http://${LAN}:8000"
fi
echo
echo "  关掉这个窗口就停。"
echo

if command -v open >/dev/null 2>&1; then
  open "http://localhost:8000" || true
fi

exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
