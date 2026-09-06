"""HTTP：健康检查与云上还原。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Header, UploadFile

from .. import db, restore
from ..deps import get_conn

router = APIRouter()


@router.get("/api/health")
def api_health(conn: sqlite3.Connection = Depends(get_conn)):
    beans = conn.execute("SELECT COUNT(*) FROM bean").fetchone()[0]
    bottles = conn.execute("SELECT COUNT(*) FROM bottle").fetchone()[0]
    return {"ok": True, "beans": beans, "spirits": bottles, "db": str(db.db_path())}


@router.post("/api/ops/restore")
async def api_restore(
    file: UploadFile = File(...),
    x_restore_key: str | None = Header(default=None, alias="X-Restore-Key"),
):
    """把 backup.bat 的 zip 解到数据盘。上传后请在 Render 里手动重启一次。"""
    restore.require_key(x_restore_key)
    return restore.apply_zip(file)
