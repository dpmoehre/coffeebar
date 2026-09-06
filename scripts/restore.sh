#!/usr/bin/env bash
# 用法：bash scripts/restore.sh 备份.zip [--dest 目录] [--force]
# 还原到临时目录做演练：bash scripts/restore.sh xx.zip --dest /tmp/cb-restore --force
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -lt 1 ]]; then
  echo "  用法：bash scripts/restore.sh 备份.zip [--dest 目录] [--force]"
  exit 1
fi
uv run python -m app.backup restore "$@"
