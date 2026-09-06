#!/usr/bin/env bash
# Mac / Linux：库 + 照片打成 zip。COFFEEBAR_BACKUP_DIR 可指到第二块盘 / 群晖挂载。
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m app.backup pack
