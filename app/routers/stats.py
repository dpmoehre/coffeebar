"""HTTP：统计、今天条、日历、出表。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import db, gear, ledger, stats, today
from ..deps import current_account, get_conn

router = APIRouter()


# ── 统计 / 补货 ─────────────────────────────────────────────


@router.get("/api/stats")
def api_stats(
    period: str = "month",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return stats.summary(conn, period, owner_id=account["id"])


@router.get("/api/restock")
def api_restock(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {
        "items": stats.restock_list(conn, owner_id=account["id"]),
        "spirits": stats.restock_spirits(conn, owner_id=account["id"]),
        "filters": gear.restock_filters(conn, account["id"]),
    }


@router.get("/api/today")
def api_today(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """豆库顶上「今天」条。当前账号、当前业务日；不占写锁。"""
    return today.snapshot(conn, account["id"])


@router.get("/api/calendar")
def api_calendar(
    year: int | None = None,
    month: int | None = None,
    person_id: int | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    now = db.parse(db.now())
    y = year or now.year
    m = month or now.month
    if y < 2000 or y > 2100 or m < 1 or m > 12:
        raise HTTPException(400, "年月不对")
    if person_id is not None:
        row = conn.execute(
            "SELECT id FROM person WHERE id = ? AND owner_id = ?",
            (person_id, account["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "没有这个人")
    return ledger.month(conn, y, m, account["id"], person_id)


@router.get("/api/calendar/day")
def api_calendar_day(
    date: str,
    person_id: int | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "日期不对")
    if person_id is not None:
        row = conn.execute(
            "SELECT id FROM person WHERE id = ? AND owner_id = ?",
            (person_id, account["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "没有这个人")
    return ledger.day(conn, date, account["id"], person_id)


@router.get("/api/export")
def api_export(
    period: str = "month",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    if period not in ("week", "month", "year", "all"):
        raise HTTPException(400, "期间不对")
    raw = ledger.export_zip(conn, account["id"], period)
    name = f"coffeebar-{period}.zip"
    return Response(
        content=raw,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )

