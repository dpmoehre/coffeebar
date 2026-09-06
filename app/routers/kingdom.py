"""HTTP：王国豆子 / 器具与收录。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from .. import kingdom, kingdom_gear, ratelimit
from ..deps import current_account, current_admin, get_conn

router = APIRouter()


@router.get("/api/kingdom")
def api_kingdom_list(
    saved: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    only = saved in ("1", "true", "yes")
    return {"beans": kingdom.list_kingdom(conn, account["id"], saved=only)}


@router.get("/api/kingdom/gear")
def api_kingdom_gear_list(
    saved: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    only = saved in ("1", "true", "yes")
    return {"gear": kingdom_gear.list_kingdom_gear(conn, account["id"], saved=only)}


@router.get("/api/kingdom/gear/{catalog_id}")
def api_kingdom_gear_get(
    catalog_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    card = kingdom_gear.get_kingdom_gear(conn, catalog_id, account["id"])
    if not card:
        raise HTTPException(404, "王国里没有这件器具")
    return card


@router.put("/api/kingdom/gear/{catalog_id}/score")
def api_kingdom_gear_score(
    catalog_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return kingdom_gear.upsert_score(conn, catalog_id, account["id"], payload or {})


@router.delete("/api/kingdom/gear/{catalog_id}/score")
def api_kingdom_gear_unscore(
    catalog_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    card = kingdom_gear.get_kingdom_gear(conn, catalog_id, account["id"])
    if not card:
        raise HTTPException(404, "王国里没有这件器具")
    return kingdom_gear.delete_score(conn, catalog_id, account["id"])


@router.post("/api/kingdom/gear/{catalog_id}/score/photos", status_code=201)
async def api_add_kingdom_gear_score_photo(
    catalog_id: int,
    request: Request,
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    return kingdom_gear.add_score_photo(
        conn, catalog_id, account["id"], await file.read(), file.filename or ""
    )


@router.delete("/api/kingdom-gear-score-photos/{photo_id}")
def api_del_kingdom_gear_score_photo(
    photo_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return kingdom_gear.delete_score_photo(conn, photo_id, account["id"])


@router.post("/api/kingdom/gear/{catalog_id}/favorite")
def api_kingdom_gear_fav(
    catalog_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return kingdom_gear.toggle_favorite(conn, catalog_id, account["id"])


@router.get("/api/kingdom/{kingdom_id}")
def api_kingdom_get(
    kingdom_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    card = kingdom.get_kingdom(conn, kingdom_id, account["id"])
    if not card:
        raise HTTPException(404, "王国里没有这一支")
    return card


@router.put("/api/kingdom/{kingdom_id}/score")
def api_kingdom_score(
    kingdom_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return kingdom.upsert_score(conn, kingdom_id, account["id"], payload or {})


@router.delete("/api/kingdom/{kingdom_id}/score")
def api_kingdom_unscore(
    kingdom_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    card = kingdom.get_kingdom(conn, kingdom_id, account["id"])
    if not card:
        raise HTTPException(404, "王国里没有这一支")
    return kingdom.delete_score(conn, kingdom_id, account["id"])


@router.post("/api/kingdom/{kingdom_id}/score/photos", status_code=201)
async def api_add_kingdom_score_photo(
    kingdom_id: int,
    request: Request,
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    return kingdom.add_score_photo(
        conn, kingdom_id, account["id"], await file.read(), file.filename or ""
    )


@router.delete("/api/kingdom-score-photos/{photo_id}")
def api_del_kingdom_score_photo(
    photo_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return kingdom.delete_score_photo(conn, photo_id, account["id"])


@router.post("/api/kingdom/{kingdom_id}/favorite")
def api_kingdom_fav(
    kingdom_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return kingdom.toggle_favorite(conn, kingdom_id, account["id"])


@router.get("/api/admin/kingdom/queue")
def api_admin_kingdom_queue(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return {"queue": kingdom.queue(conn), "beans": kingdom.list_kingdom(conn, account["id"])}


@router.post("/api/admin/kingdom/collect/{bean_id}")
def api_admin_kingdom_collect(
    bean_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return kingdom.collect(conn, account, bean_id, payload or {})


@router.patch("/api/admin/kingdom/{kingdom_id}")
def api_admin_kingdom_patch(
    kingdom_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return kingdom.update_kingdom(conn, kingdom_id, payload or {})
