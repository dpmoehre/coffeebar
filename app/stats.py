"""平均每杯粉量与统计汇总。

两条硬口径（见 docs/002）：
- 所有汇总**排除已撤回**（voided_at 非空）的流水
- 杯数一律按**平均每杯粉量**换算，不用假想的 15 g
"""

from __future__ import annotations

import sqlite3

from . import db

FALLBACK_DOSE = 15.0   # 一杯都还没冲过时的兜底
BEAN_WINDOW = 20       # 这支豆看最近多少杯
GLOBAL_WINDOW = 50     # 全吧台看最近多少杯

# 账面剩余表达式（与 store.BALANCE 同一口径，供聚合查询内联）
BALANCE_EXPR = """
    COALESCE(l.measured_g, l.nominal_g)
    + COALESCE((SELECT SUM(delta_g) FROM stock_event WHERE lot_id = l.id), 0)
    - COALESCE((SELECT SUM(amount_g) FROM consumption_event
                WHERE lot_id = l.id AND voided_at IS NULL), 0)
"""


def average_dose(conn: sqlite3.Connection, bean_id: int | None = None) -> dict:
    """就近优先：这支豆最近 20 杯 → 全局最近 50 杯 → 兜底 15 g。

    同时给区间，只给一个平均值会掩盖波动。
    """
    if bean_id is not None:
        got = _avg_from(conn, "l.bean_id = ?", (bean_id,), BEAN_WINDOW)
        if got:
            return {**got, "source": "bean"}

    got = _avg_from(conn, "1 = 1", (), GLOBAL_WINDOW)
    if got:
        return {**got, "source": "global"}

    return {
        "avg_g": FALLBACK_DOSE,
        "lo_g": None,
        "hi_g": None,
        "cups": 0,
        "source": "fallback",
    }


def _avg_from(conn: sqlite3.Connection, where: str, args: tuple, window: int) -> dict | None:
    cur = conn.execute(
        f"""SELECT amount_g FROM consumption_event c
            JOIN bean_lot l ON l.id = c.lot_id
            WHERE c.kind = 'coffee' AND c.voided_at IS NULL AND {where}
            ORDER BY c.at DESC, c.id DESC LIMIT ?""",
        (*args, window),
    )
    gs = [r[0] for r in cur.fetchall()]
    if not gs:
        return None
    return {
        "avg_g": round(sum(gs) / len(gs), 1),
        "lo_g": min(gs),
        "hi_g": max(gs),
        "cups": len(gs),
    }


def cups_left(balance_g: float, avg_g: float) -> int:
    if avg_g <= 0:
        return 0
    return int(balance_g // avg_g)


def daily_rate(conn: sqlite3.Connection, bean_id: int, days: int = 14) -> float:
    """近 N 天日均消耗克数，用于估「还能撑几天」。"""
    cur = conn.execute(
        """SELECT COALESCE(SUM(c.amount_g), 0) FROM consumption_event c
           JOIN bean_lot l ON l.id = c.lot_id
           WHERE l.bean_id = ? AND c.voided_at IS NULL
             AND c.at >= datetime('now', 'localtime', ?)""",
        (bean_id, f"-{days} days"),
    )
    total = cur.fetchone()[0] or 0
    return total / days


def summary(conn: sqlite3.Connection, period: str = "month") -> dict:
    """统计页顶部的数字。period: week / month / year / all"""
    start = db.period_start(period)
    where = "c.voided_at IS NULL AND c.kind = 'coffee'"
    args: tuple = ()
    if start:
        where += " AND c.at >= ?"
        args = (start,)

    row = conn.execute(
        f"""SELECT COALESCE(SUM(c.amount_g), 0) AS beans_g,
                   COUNT(*)                     AS cups,
                   COALESCE(SUM(c.amount_g * COALESCE(c.unit_cost, 0)), 0) AS spent
            FROM consumption_event c WHERE {where}""",
        args,
    ).fetchone()

    beans_g, cups, spent = row[0], row[1], row[2]

    # 买进来的钱：期间新建批次的买入价合计，和「喝掉的钱」分开
    bought_where = "1 = 1"
    bought_args: tuple = ()
    if start:
        bought_where = "created_at >= ?"
        bought_args = (start,)
    bought = conn.execute(
        f"SELECT COALESCE(SUM(price), 0) FROM bean_lot WHERE {bought_where}", bought_args
    ).fetchone()[0]

    # 还在库约多少钱：未关袋批次的账面 × 单价
    on_hand = conn.execute(
        f"""SELECT COALESCE(SUM(
                ({BALANCE_EXPR}) * (l.price / NULLIF(COALESCE(l.measured_g, l.nominal_g), 0))
            ), 0)
            FROM bean_lot l WHERE l.closed_at IS NULL AND l.price IS NOT NULL"""
    ).fetchone()[0]

    dose = average_dose(conn)
    if cups:
        dose = {
            "avg_g": round(beans_g / cups, 1),
            "lo_g": conn.execute(
                f"SELECT MIN(c.amount_g) FROM consumption_event c WHERE {where}", args
            ).fetchone()[0],
            "hi_g": conn.execute(
                f"SELECT MAX(c.amount_g) FROM consumption_event c WHERE {where}", args
            ).fetchone()[0],
            "cups": cups,
            "source": "period",
        }

    return {
        "period": period,
        "since": start,
        "beans_g": round(beans_g, 1),
        "cups": cups,
        "avg_dose": dose,
        "spent": round(spent, 2),
        "bought": round(bought, 2),
        "on_hand": round(on_hand, 2),
        "by_person": by_person(conn, where, args),
        "by_bean": by_bean(conn, where, args),
        "daily": daily_series(conn, where, args),
    }


def by_person(conn: sqlite3.Connection, where: str, args: tuple) -> list[dict]:
    cur = conn.execute(
        f"""SELECT COALESCE(p.name, '没记') AS name,
                   COALESCE(SUM(c.amount_g), 0) AS beans_g,
                   COUNT(*) AS cups,
                   COALESCE(SUM(c.amount_g * COALESCE(c.unit_cost, 0)), 0) AS spent
            FROM consumption_event c
            LEFT JOIN person p ON p.id = c.person_id
            WHERE {where}
            GROUP BY c.person_id ORDER BY beans_g DESC""",
        args,
    )
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["avg_dose_g"] = round(d["beans_g"] / d["cups"], 1) if d["cups"] else None
        d["spent"] = round(d["spent"], 2)
        d["beans_g"] = round(d["beans_g"], 1)
        out.append(d)
    return out


def by_bean(conn: sqlite3.Connection, where: str, args: tuple) -> list[dict]:
    cur = conn.execute(
        f"""SELECT b.id, b.name,
                   COALESCE(SUM(c.amount_g), 0) AS beans_g,
                   COUNT(*) AS cups,
                   COALESCE(SUM(c.amount_g * COALESCE(c.unit_cost, 0)), 0) AS spent
            FROM consumption_event c
            JOIN bean_lot l ON l.id = c.lot_id
            JOIN bean b ON b.id = l.bean_id
            WHERE {where}
            GROUP BY b.id ORDER BY beans_g DESC LIMIT 10""",
        args,
    )
    return [
        {**dict(r), "beans_g": round(r["beans_g"], 1), "spent": round(r["spent"], 2)}
        for r in cur.fetchall()
    ]


def daily_series(conn: sqlite3.Connection, where: str, args: tuple) -> list[dict]:
    """按业务日（凌晨 4 点分界）汇总克数，画消耗速度曲线。"""
    cur = conn.execute(
        f"""SELECT date(c.at, '-{db.DAY_CUTOFF_HOURS} hours') AS day,
                   COALESCE(SUM(c.amount_g), 0) AS beans_g,
                   COUNT(*) AS cups
            FROM consumption_event c WHERE {where}
            GROUP BY day ORDER BY day""",
        args,
    )
    return [{"day": r[0], "beans_g": round(r[1], 1), "cups": r[2]} for r in cur.fetchall()]


def restock_list(conn: sqlite3.Connection) -> list[dict]:
    """低于安全库存，或按消耗速度估「还能撑的天数」过短的豆。"""
    beans = conn.execute(
        f"""SELECT b.id, b.name, b.roast,
                   COALESCE((SELECT SUM({BALANCE_EXPR}) FROM bean_lot l
                              WHERE l.bean_id = b.id AND l.closed_at IS NULL), 0) AS balance_g,
                   (SELECT COUNT(*) FROM bean_lot l
                     WHERE l.bean_id = b.id AND l.closed_at IS NULL) AS open_lots,
                   COALESCE(r.min_g, 0)    AS min_g,
                   COALESCE(r.min_days, 3) AS min_days,
                   (SELECT price FROM bean_lot l WHERE l.bean_id = b.id
                     ORDER BY l.created_at DESC LIMIT 1) AS last_price
            FROM bean b LEFT JOIN restock_rule r ON r.bean_id = b.id"""
    ).fetchall()

    out = []
    for b in beans:
        d = dict(b)
        avg = average_dose(conn, d["id"])
        rate = daily_rate(conn, d["id"])
        days = (d["balance_g"] / rate) if rate > 0 else None
        reasons = []
        if d["open_lots"] == 0:
            reasons.append("在库没有了")
        else:
            if d["min_g"] and d["balance_g"] < d["min_g"]:
                reasons.append(f"低于安全库存 {d['min_g']:g} g")
            if d["balance_g"] < avg["avg_g"]:
                reasons.append("不够一杯了")
            if days is not None and days < d["min_days"]:
                reasons.append(f"照这个喝法只够 {days:.1f} 天")
        if not reasons:
            continue
        d["balance_g"] = round(d["balance_g"], 1)
        d["cups_left"] = cups_left(d["balance_g"], avg["avg_g"])
        d["days_left"] = round(days, 1) if days is not None else None
        d["reasons"] = reasons
        d["photos"] = [
            dict(r)
            for r in conn.execute(
                "SELECT id, path, note FROM restock_photo WHERE bean_id = ? ORDER BY created_at DESC",
                (d["id"],),
            ).fetchall()
        ]
        out.append(d)
    return out


def person_profile(conn: sqlite3.Connection, person_id: int) -> dict:
    """画像：这个人的数字 + 常喝 + 口味倾向。"""
    person = conn.execute("SELECT * FROM person WHERE id = ?", (person_id,)).fetchone()
    if not person:
        return {}
    where = "c.voided_at IS NULL AND c.kind = 'coffee' AND c.person_id = ?"
    args = (person_id,)

    row = conn.execute(
        f"""SELECT COALESCE(SUM(c.amount_g), 0), COUNT(*),
                   COALESCE(SUM(c.amount_g * COALESCE(c.unit_cost, 0)), 0)
            FROM consumption_event c WHERE {where}""",
        args,
    ).fetchone()

    beans_g, cups, spent = row[0], row[1], row[2]
    top = by_bean(conn, where, args)

    taste = conn.execute(
        f"""SELECT AVG(s.acidity), AVG(s.sweetness), AVG(s.dry)
            FROM consumption_event c
            JOIN bean_lot l ON l.id = c.lot_id
            JOIN bean_score s ON s.bean_id = l.bean_id
            WHERE {where}""",
        args,
    ).fetchone()

    return {
        "id": person_id,
        "name": person["name"],
        "active": bool(person["active"]),
        "beans_g": round(beans_g, 1),
        "cups": cups,
        "spent": round(spent, 2),
        "avg_dose_g": round(beans_g / cups, 1) if cups else None,
        "top_beans": top,
        "taste": {
            "acidity": round(taste[0], 1) if taste[0] else None,
            "sweetness": round(taste[1], 1) if taste[1] else None,
            "dry": round(taste[2], 1) if taste[2] else None,
        },
        "enough_sample": cups >= 3,
    }
