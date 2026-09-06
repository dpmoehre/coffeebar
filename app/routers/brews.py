"""HTTP：冲一次与撤回。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile

from .. import auth, locks, photos, ratelimit, store
from ..deps import current_account, get_conn

router = APIRouter()


# ── 冲一次 / 撤回 ───────────────────────────────────────────


@router.post("/api/brews", status_code=201)
def api_record_brew(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    """记一次冲煮。lot_id 由人选，amount_g 是当次实际粉量。"""
    lot = store.get_lot(conn, int(payload["lot_id"]))
    if not lot:
        raise HTTPException(404, "没有这一袋")
    auth.assert_owner(auth.bean_owner(conn, lot["bean_id"]), account["id"], "没有这一袋")
    locks.check(conn, f"bean:{lot['bean_id']}", x_session, x_source)
    return store.record_brew(conn, {**payload, "owner_id": account["id"]})


@router.get("/api/consumption")
def api_consumption(
    bean_id: int | None = None,
    person_id: int | None = None,
    limit: int = 50,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {
        "rows": store.list_consumption(
            conn, bean_id=bean_id, person_id=person_id, owner_id=account["id"], limit=limit
        )
    }


@router.post("/api/consumption/{cons_id}/void")
def api_void(
    cons_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """撤回：只划掉不删。"""
    auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    return store.void_consumption(conn, cons_id, (payload or {}).get("reason"))


@router.post("/api/consumption/{cons_id}/unvoid")
def api_unvoid(
    cons_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    store.unvoid_consumption(conn, cons_id)
    return {"ok": True}


@router.delete("/api/consumption/{cons_id}")
def api_delete_voided(
    cons_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """彻底删：只接受已经撤回的行，库存不再动。"""
    auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    return store.delete_voided_consumption(conn, cons_id)


@router.post("/api/consumption/{cons_id}/photos", status_code=201)
async def api_add_consumption_photo(
    cons_id: int,
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("bed"),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """给一笔冲煮挂过程照。beans 称豆 / bed 粉床 / finish 冲完 / gear 器具。"""
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    if conn.execute("SELECT id FROM consumption_event WHERE id = ?", (cons_id,)).fetchone():
        auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    return photos.attach_consumption_photo(
        conn, cons_id, kind, await file.read(), file.filename or ""
    )


@router.delete("/api/consumption-photos/{photo_id}")
def api_del_consumption_photo(
    photo_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    row = conn.execute("SELECT cons_id FROM consumption_photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        raise HTTPException(404, "没有这张图")
    auth.assert_owner(auth.consumption_owner(conn, row["cons_id"]), account["id"], "没有这张图")
    photos.delete_consumption_photo(conn, photo_id)
    return {"ok": True}


@router.post("/api/consumption/{cons_id}/person")
def api_reassign(
    cons_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """人选错了：只改归属，库存不动。"""
    auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    store.reassign_person(conn, cons_id, payload.get("person"), owner_id=account["id"])
    return {"ok": True}

