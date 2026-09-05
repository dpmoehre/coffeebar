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


def average_dose(
    conn: sqlite3.Connection, bean_id: int | None = None, owner_id: int | None = None
) -> dict:
    """就近优先：这支豆最近 20 杯 → 全局最近 50 杯 → 兜底 15 g。

    同时给区间，只给一个平均值会掩盖波动。
    """
    if bean_id is not None:
        got = _avg_from(conn, "l.bean_id = ?", (bean_id,), BEAN_WINDOW)
        if got:
            return {**got, "source": "bean"}

    extra, extra_args = "1 = 1", ()
    if owner_id is not None:
        extra = "EXISTS (SELECT 1 FROM bean b WHERE b.id = l.bean_id AND b.owner_id = ?)"
        extra_args = (owner_id,)
    got = _avg_from(conn, extra, extra_args, GLOBAL_WINDOW)
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
            WHERE c.kind = 'coffee' AND c.voided_at IS NULL
              AND COALESCE(c.as_cup, 1) = 1 AND {where}
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


def summary(conn: sqlite3.Connection, period: str = "month", owner_id: int | None = None) -> dict:
    """统计页顶部的数字。period: week / month / year / all"""
    start = db.period_start(period)
    where = "c.voided_at IS NULL AND c.kind = 'coffee'"
    args: list = []
    if owner_id is not None:
        where += (
            " AND EXISTS (SELECT 1 FROM bean_lot l JOIN bean b ON b.id = l.bean_id"
            " WHERE l.id = c.lot_id AND b.owner_id = ?)"
        )
        args.append(owner_id)
    if start:
        where += " AND c.at >= ?"
        args.append(start)

    row = conn.execute(
        f"""SELECT COALESCE(SUM(c.amount_g), 0) AS beans_g,
                   COALESCE(SUM(CASE WHEN COALESCE(c.as_cup, 1) = 1 THEN 1 ELSE 0 END), 0) AS cups,
                   COALESCE(SUM(CASE WHEN COALESCE(c.as_cup, 1) = 1 THEN c.amount_g ELSE 0 END), 0)
                       AS cup_g,
                   COALESCE(SUM(c.amount_g * COALESCE(c.unit_cost, 0)), 0) AS spent
            FROM consumption_event c WHERE {where}""",
        args,
    ).fetchone()

    beans_g, cups, cup_g, spent = row[0], row[1], row[2], row[3]

    # 买进来的钱：期间新建批次的买入价合计，和「喝掉的钱」分开
    bean_lot_where, bottle_lot_where = "1 = 1", "1 = 1"
    bean_lot_args: list = []
    bottle_lot_args: list = []
    if owner_id is not None:
        bean_lot_where = "bean_id IN (SELECT id FROM bean WHERE owner_id = ?)"
        bottle_lot_where = "bottle_id IN (SELECT id FROM bottle WHERE owner_id = ?)"
        bean_lot_args.append(owner_id)
        bottle_lot_args.append(owner_id)
    if start:
        bean_lot_where += " AND created_at >= ?"
        bottle_lot_where += " AND created_at >= ?"
        bean_lot_args.append(start)
        bottle_lot_args.append(start)
    bought_beans = conn.execute(
        f"SELECT COALESCE(SUM(price), 0) FROM bean_lot WHERE {bean_lot_where}", bean_lot_args
    ).fetchone()[0]
    bought_bottles = conn.execute(
        f"SELECT COALESCE(SUM(price), 0) FROM bottle_lot WHERE {bottle_lot_where}", bottle_lot_args
    ).fetchone()[0]
    bought = bought_beans + bought_bottles

    # 还在库约多少钱：未关袋/未关瓶的账面 × 单价
    on_hand_bean_where = (
        "l.closed_at IS NULL AND l.price IS NOT NULL"
        " AND EXISTS (SELECT 1 FROM bean b WHERE b.id = l.bean_id AND b.deleted_at IS NULL)"
    )
    on_hand_bottle_where = "l.closed_at IS NULL AND l.price IS NOT NULL"
    on_hand_bean_args: list = []
    on_hand_bottle_args: list = []
    if owner_id is not None:
        on_hand_bean_where += " AND l.bean_id IN (SELECT id FROM bean WHERE owner_id = ?)"
        on_hand_bottle_where += " AND l.bottle_id IN (SELECT id FROM bottle WHERE owner_id = ?)"
        on_hand_bean_args.append(owner_id)
        on_hand_bottle_args.append(owner_id)
    on_hand_beans = conn.execute(
        f"""SELECT COALESCE(SUM(
                ({BALANCE_EXPR}) * (l.price / NULLIF(COALESCE(l.measured_g, l.nominal_g), 0))
            ), 0)
            FROM bean_lot l WHERE {on_hand_bean_where}""",
        on_hand_bean_args,
    ).fetchone()[0]
    on_hand_bottles = conn.execute(
        f"""SELECT COALESCE(SUM(
                (l.nominal_ml
                 + COALESCE((SELECT SUM(delta_ml) FROM bottle_stock_event WHERE lot_id = l.id), 0)
                 - COALESCE((SELECT SUM(amount_ml) FROM consumption_event
                             WHERE bottle_lot_id = l.id AND voided_at IS NULL), 0)
                ) * (l.price / NULLIF(l.nominal_ml, 0))
            ), 0)
            FROM bottle_lot l WHERE {on_hand_bottle_where}""",
        on_hand_bottle_args,
    ).fetchone()[0]
    on_hand = on_hand_beans + on_hand_bottles

    drink_where = "c.voided_at IS NULL AND c.kind = 'drink'"
    drink_args: list = []
    if owner_id is not None:
        drink_where += " AND b.owner_id = ?"
        drink_args.append(owner_id)
    if start:
        drink_where += " AND c.at >= ?"
        drink_args.append(start)
    from . import menu as menu_mod

    drink = conn.execute(
        f"""SELECT COALESCE(SUM(c.amount_ml), 0),
                   {menu_mod.drink_cups_sql("c")},
                   COALESCE(SUM(c.amount_ml * COALESCE(c.unit_cost, 0)), 0),
                   COALESCE(SUM(c.amount_ml * (COALESCE(b.abv, 0) / 100.0) * 0.789), 0)
            FROM consumption_event c
            LEFT JOIN bottle_lot l ON l.id = c.bottle_lot_id
            LEFT JOIN bottle b ON b.id = l.bottle_id
            WHERE {drink_where}""",
        drink_args,
    ).fetchone()
    drinks_ml, drink_cups, drink_spent, alcohol_g = drink

    dose = average_dose(conn, owner_id=owner_id)
    if cups:
        cup_where = f"{where} AND COALESCE(c.as_cup, 1) = 1"
        dose = {
            "avg_g": round(cup_g / cups, 1),
            "lo_g": conn.execute(
                f"SELECT MIN(c.amount_g) FROM consumption_event c WHERE {cup_where}", args
            ).fetchone()[0],
            "hi_g": conn.execute(
                f"SELECT MAX(c.amount_g) FROM consumption_event c WHERE {cup_where}", args
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
        "drinks_ml": round(drinks_ml, 1),
        "drink_cups": int(drink_cups or 0),
        "alcohol_g": round(alcohol_g, 1),
        "spent": round(spent + drink_spent, 2),
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
            WHERE {where} AND COALESCE(c.as_cup, 1) = 1
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
                   COALESCE(SUM(CASE WHEN COALESCE(c.as_cup, 1) = 1 THEN 1 ELSE 0 END), 0) AS cups,
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
                   COALESCE(SUM(CASE WHEN COALESCE(c.as_cup, 1) = 1 THEN 1 ELSE 0 END), 0) AS cups
            FROM consumption_event c WHERE {where}
            GROUP BY day ORDER BY day""",
        args,
    )
    return [{"day": r[0], "beans_g": round(r[1], 1), "cups": r[2]} for r in cur.fetchall()]


def restock_list(conn: sqlite3.Connection, owner_id: int | None = None) -> list[dict]:
    """低于安全库存，或按消耗速度估「还能撑的天数」过短的豆。"""
    beans = conn.execute(
        f"""SELECT b.id, b.name, b.roast,
                   COALESCE((SELECT SUM({BALANCE_EXPR}) FROM bean_lot l
                              WHERE l.bean_id = b.id AND l.closed_at IS NULL), 0) AS balance_g,
                   (SELECT COUNT(*) FROM bean_lot l
                     WHERE l.bean_id = b.id AND l.closed_at IS NULL) AS open_lots,
                   (SELECT COUNT(*) FROM bean_lot l WHERE l.bean_id = b.id) AS all_lots,
                   COALESCE(r.min_g, 0)    AS min_g,
                   COALESCE(r.min_days, 3) AS min_days,
                   (SELECT price FROM bean_lot l WHERE l.bean_id = b.id
                     ORDER BY l.created_at DESC LIMIT 1) AS last_price
            FROM bean b LEFT JOIN restock_rule r ON r.bean_id = b.id
            WHERE (? IS NULL OR b.owner_id = ?)
              AND b.deleted_at IS NULL""",
        (owner_id, owner_id),
    ).fetchall()

    out = []
    for b in beans:
        d = dict(b)
        avg = average_dose(conn, d["id"])
        rate = daily_rate(conn, d["id"])
        days = (d["balance_g"] / rate) if rate > 0 else None
        reasons = []
        if d["all_lots"] == 0:
            # 只建了豆卡还没入袋：豆子在手上，缺的是称重录入，不是缺货
            continue
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


def person_profile(
    conn: sqlite3.Connection, person_id: int, owner_id: int | None = None
) -> dict:
    """画像：这个人的数字 + 常喝 + 口味倾向。"""
    person = conn.execute("SELECT * FROM person WHERE id = ?", (person_id,)).fetchone()
    if not person:
        return {}
    if owner_id is not None and person["owner_id"] != owner_id:
        return {}
    where = (
        "c.voided_at IS NULL AND c.kind = 'coffee' AND c.person_id = ?"
        " AND COALESCE(c.as_cup, 1) = 1"
    )
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
