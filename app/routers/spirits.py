"""HTTP：基酒与倒酒。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile

from .. import auth, locks, photos, ratelimit, spirits, store
from ..deps import current_account, get_conn

router = APIRouter()


# ── 基酒 ────────────────────────────────────────────────────


@router.get("/api/spirits")
def api_spirits(
    scope: str = "stock",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    items = spirits.list_spirits(conn, scope, owner_id=account["id"])
    for s in items:
        s["cover"] = photos.cover(photos.list_bottle_photos(conn, s["id"]))
    return {"spirits": items, "kinds": spirits.KINDS}


@router.post("/api/spirits", status_code=201)
def api_create_spirit(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    if not payload.get("name", "").strip():
        raise store.Conflict("酒得有个名字")
    payload = {**payload, "owner_id": account["id"]}
    bottle_id = spirits.create_spirit(conn, payload)
    if payload.get("nominal_ml"):
        spirits.add_lot(conn, bottle_id, payload)
    return spirits.get_spirit(conn, bottle_id, owner_id=account["id"])


@router.get("/api/spirits/{bottle_id}")
def api_spirit(
    bottle_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    bottle = spirits.get_spirit(conn, bottle_id, owner_id=account["id"])
    if not bottle:
        raise HTTPException(404, "没有这支酒")
    bottle["photos"] = photos.list_bottle_photos(conn, bottle_id)
    bottle["log"] = store.list_consumption(conn, bottle_id=bottle_id, owner_id=account["id"], limit=30)
    bottle["lock"] = locks.status(conn, f"bottle:{bottle_id}")
    return bottle


@router.patch("/api/spirits/{bottle_id}")
def api_update_spirit(
    bottle_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(auth.spirit_owner(conn, bottle_id), account["id"], "没有这支酒")
    locks.check(conn, f"bottle:{bottle_id}", x_session, x_source)
    spirits.update_spirit(conn, bottle_id, payload)
    return spirits.get_spirit(conn, bottle_id, owner_id=account["id"])


@router.delete("/api/spirits/{bottle_id}")
def api_delete_spirit(
    bottle_id: int,
    mode: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    """从酒库拿掉一张卡。有未撤回倒酒时带 mode=keep（留下花掉的钱）或 wipe（连记录一起抹）。"""
    auth.assert_owner(auth.spirit_owner(conn, bottle_id), account["id"], "没有这支酒")
    locks.check(conn, f"bottle:{bottle_id}", x_session, x_source)
    return spirits.delete_spirit(conn, bottle_id, mode=mode)


@router.post("/api/spirits/{bottle_id}/lots", status_code=201)
def api_add_bottle_lot(
    bottle_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(auth.spirit_owner(conn, bottle_id), account["id"], "没有这支酒")
    locks.check(conn, f"bottle:{bottle_id}", x_session, x_source)
    spirits.add_lot(conn, bottle_id, payload)
    return spirits.get_spirit(conn, bottle_id, owner_id=account["id"])


@router.post("/api/spirits/{bottle_id}/photos", status_code=201)
async def api_add_bottle_photo(
    bottle_id: int,
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("pack"),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    auth.assert_owner(auth.spirit_owner(conn, bottle_id), account["id"], "没有这支酒")
    return photos.attach_bottle_photo(conn, bottle_id, kind, await file.read(), file.filename or "")


@router.post("/api/bottle-lots/{lot_id}/open")
def api_open_bottle(
    lot_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.bottle_lot_owner(conn, lot_id), account["id"], "没有这一瓶")
    spirits.open_lot(conn, lot_id)
    return spirits.get_lot(conn, lot_id)


@router.post("/api/bottle-lots/{lot_id}/adjust")
def api_adjust_bottle(
    lot_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.bottle_lot_owner(conn, lot_id), account["id"], "没有这一瓶")
    return spirits.adjust_lot(conn, lot_id, float(payload["actual_ml"]), payload.get("note"))


@router.post("/api/bottle-lots/{lot_id}/close")
def api_close_bottle(
    lot_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.bottle_lot_owner(conn, lot_id), account["id"], "没有这一瓶")
    body = payload or {}
    return spirits.close_lot(conn, lot_id, body.get("note"))


@router.post("/api/drinks", status_code=201)
def api_record_drink(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    lot = spirits.get_lot(conn, int(payload["lot_id"]))
    if not lot:
        raise HTTPException(404, "没有这一瓶")
    auth.assert_owner(auth.spirit_owner(conn, lot["bottle_id"]), account["id"], "没有这一瓶")
    return spirits.record_drink(conn, {**payload, "owner_id": account["id"]})

