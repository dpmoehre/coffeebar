"""拉起仓库 .venv 里的 coffeebar-mcp。给 Cursor 用，不依赖某一台的绝对路径。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
unix = ROOT / ".venv" / "bin" / "coffeebar-mcp"
win = ROOT / ".venv" / "Scripts" / "coffeebar-mcp.exe"
exe = win if os.name == "nt" else unix
if not exe.is_file():
    sys.stderr.write(f"找不到 {exe}。先在仓库根目录跑 install 脚本。\n")
    raise SystemExit(1)
os.chdir(ROOT)
os.execv(str(exe), [str(exe), *sys.argv[1:]])
