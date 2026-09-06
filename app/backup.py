"""本机备份 / 还原。zip 格式与 backup.sh、云上 restore 相同：coffeebar.db + photos/。"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from . import db, restore

KEEP = 14
HOME_DIR = Path.home() / "coffeebar-backup"
LOCAL_WARN = "这份备份还在本机，盘坏会一起没"


def backup_dir() -> Path:
    raw = (os.environ.get("COFFEEBAR_BACKUP_DIR") or "").strip()
    return Path(raw).expanduser() if raw else HOME_DIR


def is_local_home(path: Path) -> bool:
    try:
        resolved = path.resolve()
        home = Path.home().resolve()
        return resolved == home or home in resolved.parents or resolved == HOME_DIR.resolve()
    except OSError:
        return True


def prune(folder: Path, keep: int = KEEP) -> list[Path]:
    zips = sorted(folder.glob("coffeebar-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    dropped: list[Path] = []
    for old in zips[keep:]:
        old.unlink(missing_ok=True)
        dropped.append(old)
    return dropped


def write_zip(dest: Path, data_dir: Path | None = None) -> Path:
    data_dir = data_dir or db.DATA_DIR
    db_file = data_dir / "coffeebar.db"
    if not db_file.is_file():
        raise FileNotFoundError("还没有数据可以备份。")
    dest.parent.mkdir(parents=True, exist_ok=True)
    snap = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    snap.close()
    try:
        src = sqlite3.connect(str(db_file))
        dst = sqlite3.connect(snap.name)
        src.backup(dst)
        dst.close()
        src.close()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snap.name, "coffeebar.db")
            photos = data_dir / "photos"
            if photos.is_dir():
                for p in photos.rglob("*"):
                    if p.is_file():
                        zf.write(p, Path("photos") / p.relative_to(photos))
    finally:
        Path(snap.name).unlink(missing_ok=True)
    return dest


def pack(out_dir: Path | None = None, data_dir: Path | None = None) -> tuple[Path, bool]:
    folder = out_dir or backup_dir()
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    dest = folder / f"coffeebar-{stamp}.zip"
    write_zip(dest, data_dir)
    prune(folder)
    return dest, is_local_home(folder)


def extract_zip(zip_path: Path, dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    raw = zip_path.read_bytes()
    if len(raw) < 22:
        raise ValueError("这不像一份备份")
    tmp = Path(tempfile.mkdtemp(prefix="coffeebar-restore-"))
    try:
        pack_path = tmp / "pack.zip"
        pack_path.write_bytes(raw)
        with zipfile.ZipFile(pack_path) as zf:
            if not any(Path(n).name == "coffeebar.db" for n in zf.namelist()):
                raise ValueError("压缩包里没有 coffeebar.db")
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.endswith("/") or ".." in Path(name).parts:
                    continue
                if Path(name).name == "coffeebar.db":
                    (tmp / "out").mkdir(exist_ok=True)
                    (tmp / "out" / "coffeebar.db").write_bytes(zf.read(info))
                elif "/photos/" in f"/{name}" or name.startswith("photos/"):
                    rel = name.split("photos/", 1)[-1]
                    if not rel or ".." in Path(rel).parts:
                        continue
                    photo = tmp / "out" / "photos" / rel
                    photo.parent.mkdir(parents=True, exist_ok=True)
                    if not info.is_dir():
                        photo.write_bytes(zf.read(info))
        db_src = tmp / "out" / "coffeebar.db"
        if not db_src.exists():
            raise ValueError("压缩包里没有 coffeebar.db")
        shutil.copy2(db_src, dest / "coffeebar.db")
        photos_src = tmp / "out" / "photos"
        photos_dst = dest / "photos"
        if photos_src.exists():
            if photos_dst.exists():
                shutil.rmtree(photos_dst)
            shutil.copytree(photos_src, photos_dst)
        return {"ok": True, "db": str(dest / "coffeebar.db"), "photos": photos_src.exists()}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def port_open(host: str = "127.0.0.1", port: int = 8000) -> bool:
    try:
        with socket.create_connection((host, port), 0.3):
            return True
    except OSError:
        return False


def apply_upload(upload) -> dict:
    """云上 restore 仍走密钥；解包逻辑共用。"""
    return restore.apply_zip(upload)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="coffeebar-backup")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pack", help="打一份 zip")
    rst = sub.add_parser("restore", help="把 zip 解到数据目录")
    rst.add_argument("zip")
    rst.add_argument("--dest", default="")
    rst.add_argument("--force", action="store_true")
    args = p.parse_args(argv)

    if args.cmd == "pack":
        dest, local = pack()
        print(f"  备份好了：{dest}")
        if local:
            print(f"  {LOCAL_WARN}")
        return 0

    dest = Path(args.dest).expanduser() if args.dest else db.DATA_DIR
    if dest.resolve() == db.DATA_DIR.resolve() and port_open() and not args.force:
        print("  服务还在跑。先停 start.sh / start.bat，或换 --dest 指到临时目录。", file=sys.stderr)
        return 2
    if dest.resolve() == db.DATA_DIR.resolve() and not args.force and dest.exists():
        print("  会盖掉现有 data/。确认的话加 --force。", file=sys.stderr)
        return 3
    out = extract_zip(Path(args.zip), dest)
    print(f"  还原好了：{out['db']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
