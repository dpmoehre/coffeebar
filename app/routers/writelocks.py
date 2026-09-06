"""HTTP：写锁。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from .. import auth, locks
from ..deps import current_account, get_conn

router = APIRouter()


# ── 写锁 ────────────────────────────────────────────────────


@router.post("/api/locks/{resource}")
def api_lock(
    resource: str,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_lock_resource(conn, resource, account["id"])
    body = payload or {}
    return locks.acquire(
        conn, resource, x_session, body.get("holder"), x_source, bool(body.get("take_over"))
    )


@router.put("/api/locks/{resource}")
def api_heartbeat(
    resource: str,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
):
    auth.assert_lock_resource(conn, resource, account["id"])
    ok = locks.heartbeat(conn, resource, x_session)
    if not ok:
        return JSONResponse(
            status_code=409,
            content={"error": "taken_over", "message": "已被其他窗口接管，你这次的修改没有保存"},
        )
    return {"ok": True}


@router.delete("/api/locks/{resource}")
def api_unlock(
    resource: str,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
):
    auth.assert_lock_resource(conn, resource, account["id"])
    locks.release(conn, resource, x_session)
    return {"ok": True}
