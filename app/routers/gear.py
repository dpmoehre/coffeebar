"""HTTP：私人器具台面。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from .. import auth, gear, photos, ratelimit
from ..deps import current_account, get_conn

router = APIRouter()


# ── 咖啡器具 ────────────────────────────────────────────────


@router.get("/api/gear/meta")
def api_gear_meta():
    return gear.meta()


@router.get("/api/gear")
def api_list_gear(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"gear": gear.list_gear(conn, account["id"]), "catalog": gear.list_catalog(conn)}


@router.get("/api/gear/catalog")
def api_gear_catalog(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"catalog": gear.list_catalog(conn)}


@router.post("/api/gear", status_code=201)
def api_create_gear(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return gear.create_gear(conn, account["id"], payload or {})


@router.post("/api/gear/from-catalog/{catalog_id}", status_code=201)
def api_gear_from_catalog(
    catalog_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return gear.add_from_catalog(conn, account["id"], catalog_id)


@router.get("/api/gear/{gear_id}")
def api_get_gear(
    gear_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    item = gear.get_gear(conn, gear_id, account["id"])
    if not item:
        raise HTTPException(404, "没有这件器具")
    return item


@router.post("/api/gear/{gear_id}/packs", status_code=201)
def api_open_filter_pack(
    gear_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return gear.open_pack(conn, gear_id, account["id"], payload or {})


@router.patch("/api/gear/{gear_id}")
def api_update_gear(
    gear_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return gear.update_gear(conn, gear_id, account["id"], payload or {})


@router.delete("/api/gear/{gear_id}")
def api_delete_gear(
    gear_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    gear.delete_gear(conn, gear_id, account["id"])
    return {"ok": True}


@router.post("/api/gear/{gear_id}/photos", status_code=201)
async def api_add_gear_photo(
    gear_id: int,
    request: Request,
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    if not gear.get_gear(conn, gear_id, account["id"]):
        raise HTTPException(404, "没有这件器具")
    return photos.attach_gear_photo(conn, gear_id, await file.read(), file.filename or "")


@router.delete("/api/gear-photos/{photo_id}")
def api_del_gear_photo(
    photo_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    row = conn.execute(
        """SELECT g.owner_id FROM user_gear_photo p
             JOIN user_gear g ON g.id = p.gear_id WHERE p.id = ?""",
        (photo_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "没有这张图")
    auth.assert_owner(row["owner_id"], account["id"], "没有这张图")
    photos.delete_gear_photo(conn, photo_id)
    return {"ok": True}

