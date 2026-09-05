"""把小主机 backup.bat 打出来的 zip 解到 COFFEEBAR_DATA。只认恢复密钥。"""

from __future__ import annotations

import hmac
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from . import db


def _key() -> str:
    return (os.environ.get("COFFEEBAR_RESTORE_KEY") or "").strip()


def require_key(got: str | None) -> None:
    expected = _key()
    if not expected:
        raise HTTPException(403, "云上没配恢复密钥")
    value = (got or "").strip()
    if len(value) != len(expected) or not hmac.compare_digest(value, expected):
        raise HTTPException(403, "恢复密钥不对")


def apply_zip(upload: UploadFile) -> dict:
    dest = db.DATA_DIR
    dest.mkdir(parents=True, exist_ok=True)
    raw = upload.file.read()
    if len(raw) < 22:
        raise HTTPException(400, "这不像一份备份")
    tmp = Path(tempfile.mkdtemp(prefix="coffeebar-restore-"))
    zip_path = tmp / "pack.zip"
    zip_path.write_bytes(raw)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            if not any(Path(n).name == "coffeebar.db" for n in names):
                raise HTTPException(400, "压缩包里没有 coffeebar.db")
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.endswith("/") or ".." in Path(name).parts:
                    continue
                target = (tmp / "out" / Path(name).name) if Path(name).name == "coffeebar.db" else None
                if Path(name).name == "coffeebar.db":
                    (tmp / "out").mkdir(exist_ok=True)
                    target = tmp / "out" / "coffeebar.db"
                    target.write_bytes(zf.read(info))
                elif "/photos/" in f"/{name}" or name.startswith("photos/"):
                    rel = name.split("photos/", 1)[-1]
                    if not rel or ".." in Path(rel).parts:
                        continue
                    photo = tmp / "out" / "photos" / rel
                    photo.parent.mkdir(parents=True, exist_ok=True)
                    if info.is_dir():
                        photo.mkdir(parents=True, exist_ok=True)
                    else:
                        photo.write_bytes(zf.read(info))
        db_src = tmp / "out" / "coffeebar.db"
        if not db_src.exists():
            raise HTTPException(400, "压缩包里没有 coffeebar.db")
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
