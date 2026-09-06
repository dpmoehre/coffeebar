"""HTTP：广场公开卡。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import gear, store
from ..deps import current_account, get_conn

router = APIRouter()


def _tri_flag(value: str | None) -> bool | None:
    raw = (value or "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return None


@router.get("/api/public/beans")
def api_public_beans(
    certified: str = "any",
    q: str | None = None,
    roast: str | None = None,
    process: str | None = None,
    tag: str | None = None,
    in_kingdom: str = "any",
    sort: str = "recent",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    only = certified in ("1", "true", "yes")
    return {
        "beans": store.list_public_beans(
            conn,
            certified_only=only,
            viewer_id=account["id"],
            q=q,
            roast=roast,
            process=process,
            tags=tag,
            in_kingdom=_tri_flag(in_kingdom),
            sort=sort,
        )
    }


@router.get("/api/public/beans/{bean_id}")
def api_public_bean(
    bean_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    card = store.public_card(conn, bean_id, viewer_id=account["id"])
    if not card:
        raise HTTPException(404, "没有这张公开豆卡")
    return card


@router.post("/api/public/beans/{bean_id}/take")
def api_take_public_bean(
    bean_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    card = store.public_card(conn, bean_id, viewer_id=account["id"])
    if not card:
        raise HTTPException(404, "没有这张公开豆卡")
    if card.get("mine"):
        raise HTTPException(400, "这是你自己的卡，不用领")
    return store.take_public_bean(conn, bean_id, account["id"])


@router.get("/api/public/gear")
def api_public_gear_list(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"gear": gear.list_public_gear(conn, account["id"])}


@router.get("/api/public/gear/{gear_id}")
def api_public_gear(
    gear_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    card = gear.get_public_gear(conn, gear_id, account["id"])
    if not card:
        raise HTTPException(404, "没有这件公开器具")
    return card


@router.post("/api/public/gear/{gear_id}/take")
def api_take_public_gear(
    gear_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return gear.take_public_gear(conn, gear_id, account["id"])
