"""HTTP：后台审卡、收器具、账号。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import admin as admin_mod
from .. import gear, locks
from ..deps import current_admin, get_conn

router = APIRouter()


@router.get("/api/admin/review/beans")
def api_review_queue(
    status: str = "pending",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return {"beans": admin_mod.review_queue(conn, status)}


@router.get("/api/admin/review/beans/{bean_id}")
def api_review_bean(
    bean_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return admin_mod.review_bean(conn, bean_id)


@router.post("/api/admin/review/beans/{bean_id}/certify")
def api_certify_bean(
    bean_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    data = payload or {}
    return admin_mod.certify_bean(
        conn,
        account,
        bean_id,
        note=data.get("note") or "",
        verify_places=data.get("verify_places", True),
        force_places=bool(data.get("force_places")),
    )


@router.post("/api/admin/review/beans/{bean_id}/uncertify")
def api_uncertify_bean(
    bean_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    data = payload or {}
    return admin_mod.uncertify_bean(conn, account, bean_id, note=data.get("note") or "")


@router.put("/api/admin/review/beans/{bean_id}/places")
def api_review_set_places(
    bean_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    return admin_mod.review_set_places(conn, bean_id, payload.get("places") or [])


@router.post("/api/admin/review/beans/{bean_id}/places/guess")
def api_review_guess_places(
    bean_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    return admin_mod.review_guess_places(conn, bean_id)


@router.get("/api/admin/gear/queue")
def api_admin_gear_queue(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return {"queue": gear.queue(conn), "catalog": gear.list_catalog(conn, owners=True)}


@router.post("/api/admin/gear/catalog", status_code=201)
def api_admin_create_catalog(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return gear.create_catalog(conn, account, payload or {})


@router.patch("/api/admin/gear/catalog/{catalog_id}")
def api_admin_update_catalog(
    catalog_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return gear.update_catalog(conn, catalog_id, payload or {})


@router.delete("/api/admin/gear/catalog/{catalog_id}")
def api_admin_delete_catalog(
    catalog_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    gear.delete_catalog(conn, catalog_id)
    return {"ok": True}


@router.post("/api/admin/gear/{gear_id}/collect")
def api_admin_collect_gear(
    gear_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return gear.collect(conn, account, gear_id, payload or {})


@router.get("/api/admin/accounts")
def api_admin_accounts(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return {"accounts": admin_mod.list_accounts(conn)}


@router.get("/api/admin/accounts/{account_id}")
def api_admin_account(
    account_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return admin_mod.dossier(conn, account_id)


@router.get("/api/admin/accounts/{account_id}/beans/{bean_id}")
def api_admin_bean(
    account_id: int,
    bean_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return admin_mod.bean_detail(conn, account_id, bean_id)


@router.get("/api/admin/accounts/{account_id}/spirits/{bottle_id}")
def api_admin_spirit(
    account_id: int,
    bottle_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return admin_mod.spirit_detail(conn, account_id, bottle_id)


@router.patch("/api/admin/accounts/{account_id}")
def api_admin_patch_account(
    account_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    status = payload.get("status")
    if not status:
        raise HTTPException(400, "要改状态")
    return admin_mod.set_status(conn, account, account_id, status)


@router.post("/api/admin/accounts/{account_id}/kick")
def api_admin_kick(
    account_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_admin),
):
    return admin_mod.kick(conn, account, account_id)
