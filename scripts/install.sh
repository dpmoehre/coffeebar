#!/usr/bin/env bash
# Mac / Linux：装后端依赖、装前端并构建。对标 scripts/install.bat。
set -euo pipefail
cd "$(dirname "$0")/.."

echo
echo "  coffeebar 安装"
echo "  ========================================"
echo

if ! command -v uv >/dev/null 2>&1; then
  echo "  [1/3] 装 uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "  [1/3] uv 已经有了"
fi

echo "  [2/3] 装后端依赖..."
uv sync

if ! command -v npm >/dev/null 2>&1; then
  echo
  echo "  [3/3] 没找到 npm。去 https://nodejs.org 装 Node LTS，装完再跑一次。"
  exit 1
fi

echo "  [3/3] 装前端依赖并构建..."
(cd web && npm install && npm run build)

echo
echo "  装好了。开发机日常跑：  bash scripts/start.sh"
echo "  备份库和照片：          bash scripts/backup.sh"
echo
