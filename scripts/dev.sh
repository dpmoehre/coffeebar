#!/usr/bin/env bash
# 开发机热更新：API :8000 + Vite :5173（/api 会转到 8000）。
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d web/node_modules ]]; then
  echo "前端依赖还没装。先跑：  bash scripts/install.sh"
  exit 1
fi

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo
echo "  coffeebar 开发"
echo "  ========================================"
echo "  网页（热更新）  http://localhost:5173"
echo "  API             http://localhost:8000"
echo

uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

if command -v open >/dev/null 2>&1; then
  (sleep 1 && open "http://localhost:5173") &
fi

(cd web && npm run dev -- --host 127.0.0.1 --port 5173)
