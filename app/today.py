"""豆库顶上「今天」条。只读，不占写锁，不记消耗。"""

from __future__ import annotations

import sqlite3

from . import db, gear, stats, store
from .ledger import _DAY, _OWNER
from .menu import drink_cups_sql

MAX_PEAK = 3


def snapshot(conn: sqlite3.Connection, owner_id: int, *, day: str | None = None) -> dict:
    day = day or db.business_day(db.now())
    taste = _taste(conn, owner_id)
    restock = _restock(conn, owner_id)
    return {
        "day": day,
        "people": _people(conn, owner_id, day),
        "peak": taste["peak"],
        "stale": taste["stale"],
        "opened_long": taste["opened_long"],
        "restock": restock,
        "last_cup": _last_cup(conn, owner_id),
    }


def _bean_chip(bean: dict) -> dict:
    fresh = bean.get("freshness") or {}
    return {
        "id": bean["id"],
        "name": bean["name"],
        "days_after_roast": fresh.get("days_after_roast"),
        "label": fresh.get("label"),
        "phase": fresh.get("phase"),
        "opened_long": bool(fresh.get("opened_long")),
    }


def _people(conn: sqlite3.Connection, owner_id: int, day: str) -> list[dict]:
    coffee_sql = (
        "SUM(CASE WHEN c.kind = 'coffee' AND c.as_cup = 1 AND c.voided_at IS NULL "
        "THEN 1 ELSE 0 END)"
    )
    drink_sql = drink_cups_sql("c")
    rows = conn.execute(
        f"""SELECT c.person_id AS person_id,
                   COALESCE(p.name, '没记') AS name,
                   {coffee_sql} AS coffee,
                   {drink_sql} AS drink
            FROM consumption_event c
            LEFT JOIN person p ON p.id = c.person_id
            WHERE {_OWNER} AND {_DAY} = ?
            GROUP BY c.person_id
            HAVING {coffee_sql} > 0 OR {drink_sql} > 0
            ORDER BY coffee DESC, drink DESC, name""",
        (owner_id, owner_id, day),
    ).fetchall()
    return [
        {
            "person_id": r["person_id"],
            "name": r["name"],
            "coffee": int(r["coffee"] or 0),
            "drink": int(r["drink"] or 0),
        }
        for r in rows
    ]


def _taste(conn: sqlite3.Connection, owner_id: int) -> dict:
    beans = store.list_beans(conn, "stock", owner_id=owner_id)
    peak_src = [b for b in beans if (b.get("freshness") or {}).get("phase") == "peak"]
    peak_src.sort(
        key=lambda b: (
            (b.get("freshness") or {}).get("days_after_roast") is None,
            (b.get("freshness") or {}).get("days_after_roast") or 0,
            b.get("name") or "",
        )
    )
    peak = [_bean_chip(b) for b in peak_src[:MAX_PEAK]]

    stale_src = [b for b in beans if (b.get("freshness") or {}).get("phase") == "stale"]
    stale_src.sort(key=lambda b: -((b.get("freshness") or {}).get("days_after_roast") or 0))
    stale = _bean_chip(stale_src[0]) if stale_src else None

    shown = {b["id"] for b in peak}
    if stale:
        shown.add(stale["id"])
    long_src = [
        b
        for b in beans
        if (b.get("freshness") or {}).get("opened_long") and b["id"] not in shown
    ]
    if not long_src:
        long_src = [b for b in beans if (b.get("freshness") or {}).get("opened_long")]
    long_src.sort(key=lambda b: -((b.get("freshness") or {}).get("days_after_roast") or 0))
    opened_long = _bean_chip(long_src[0]) if long_src else None
    return {"peak": peak, "stale": stale, "opened_long": opened_long}


def _restock(conn: sqlite3.Connection, owner_id: int) -> dict:
    beans = stats.restock_list(conn, owner_id=owner_id)
    spirits = stats.restock_spirits(conn, owner_id=owner_id)
    filters = gear.restock_filters(conn, owner_id)
    return {
        "n": len(beans) + len(spirits) + len(filters),
        "beans": len(beans),
        "spirits": len(spirits),
        "filters": len(filters),
    }


def _last_cup(conn: sqlite3.Connection, owner_id: int) -> dict | None:
    row = conn.execute(
        """SELECT c.id, c.at, c.amount_g, c.brew_method, c.brew_ratio, c.brew_total_s,
                  c.person_id, p.name AS person_name,
                  b.id AS bean_id, b.name AS bean_name
             FROM consumption_event c
             JOIN bean_lot l ON l.id = c.lot_id
             JOIN bean b ON b.id = l.bean_id
             LEFT JOIN person p ON p.id = c.person_id
            WHERE b.owner_id = ? AND c.kind = 'coffee'
              AND c.as_cup = 1 AND c.voided_at IS NULL
            ORDER BY c.at DESC, c.id DESC
            LIMIT 1""",
        (owner_id,),
    ).fetchone()
    if not row:
        return None
    event = dict(row)
    event["kind"] = "coffee"
    event["as_cup"] = 1
    store.attach_brew_compare(event)
    compared = event.get("brew_compare")
    actual = compared["actual_s"] if compared else event.get("brew_total_s")
    return {
        "bean_id": event["bean_id"],
        "name": event["bean_name"],
        "person_id": event["person_id"],
        "person_name": event["person_name"],
        "at": event["at"],
        "actual_s": int(actual) if actual is not None else None,
        "planned_s": compared["planned_s"] if compared else None,
        "label": compared["label"] if compared else None,
    }
