"""HTTP：谁喝的。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, stats, store
from ..deps import current_account, get_conn

router = APIRouter()


# ── 人 ──────────────────────────────────────────────────────


@router.get("/api/people")
def api_people(
    include_inactive: bool = False,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"people": store.list_people(conn, include_inactive, owner_id=account["id"])}


@router.post("/api/people", status_code=201)
def api_add_person(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    pid = store.ensure_person(conn, payload.get("name"), account["id"])
    if pid is None:
        raise store.Conflict("名字不能为空")
    return {"id": pid, "name": payload["name"].strip()}


@router.patch("/api/people/{person_id}")
def api_patch_person(
    person_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.person_owner(conn, person_id), account["id"], "没有这个人")
    if "name" in payload:
        store.rename_person(conn, person_id, payload["name"])
    if "active" in payload:
        store.set_person_active(conn, person_id, bool(payload["active"]))
    return {"people": store.list_people(conn, include_inactive=True, owner_id=account["id"])}


@router.delete("/api/people/{person_id}")
def api_delete_person(
    person_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """删掉这个人。他名下的流水留着，只是变成「没记」。"""
    owner = auth.person_owner(conn, person_id)
    if owner is not None:
        auth.assert_owner(owner, account["id"], "没有这个人")
    out = store.delete_person(conn, person_id)
    return {**out, "people": store.list_people(conn, include_inactive=True, owner_id=account["id"])}


@router.get("/api/people/{person_id}/profile")
def api_profile(
    person_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    profile = stats.person_profile(conn, person_id, owner_id=account["id"])
    if not profile:
        raise HTTPException(404, "没有这个人")
    profile["log"] = store.list_consumption(
        conn, person_id=person_id, owner_id=account["id"], limit=50
    )
    return profile
