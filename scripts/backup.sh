#!/usr/bin/env bash
# Mac / Linux：对标 backup.bat。服务开着也能导出，库 + 照片打成 zip。
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f data/coffeebar.db ]]; then
  echo
  echo "  还没有数据可以备份。"
  echo
  exit 1
fi

STAMP=$(date +%Y-%m-%d-%H%M)
OUT="${HOME}/coffeebar-backup"
mkdir -p "$OUT"
DEST="${OUT}/coffeebar-${STAMP}.zip"
SNAP=$(mktemp)

echo
echo "  正在备份到 ${DEST}"
echo "  （豆卡照片一起打包，可能要等一会）"
echo

uv run python -c "
import sqlite3, sys
src = sqlite3.connect('data/coffeebar.db')
dst = sqlite3.connect(sys.argv[1])
src.backup(dst)
dst.close()
src.close()
" "$SNAP"

uv run python -c "
import sys, zipfile
from pathlib import Path
out, snap = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(snap, 'coffeebar.db')
    photos = Path('data/photos')
    if photos.is_dir():
        for p in photos.rglob('*'):
            if p.is_file():
                z.write(p, Path('photos') / p.relative_to(photos))
" "$DEST" "$SNAP"

rm -f "$SNAP"
echo "  备份好了：${DEST}"
echo
