"""基酒与酒瓶。

口径对齐豆子（见 docs/002）：
1. 账面剩余 = 标称毫升 + Σ bottle_stock_event.delta_ml − Σ 未撤回饮酒.amount_ml
2. 写消耗时冻结 unit_cost（元/毫升）= 买入价 ÷ 标称毫升，历史不回溯
3. 同样的酒再买一瓶只加批次，不新建酒名
"""

from __future__ import annotations

import sqlite3

from . import db, store

ETHANOL = 0.789  # 酒精密度，毫升 × (%vol/100) × 0.789 = 大约克数

USABLE = "l.nominal_ml"
BALANCE = f"""
    {USABLE}
    + COALESCE((SELECT SUM(delta_ml) FROM bottle_stock_event WHERE lot_id = l.id), 0)
    - COALESCE((SELECT SUM(amount_ml) FROM consumption_event
                WHERE bottle_lot_id = l.id AND voided_at IS NULL), 0)
"""


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _row(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


def alcohol_g(ml: float, abv: float | None) -> float | None:
    if not abv or ml <= 0:
        return None
    return round(ml * (abv / 100) * ETHANOL, 2)


def create_spirit(conn: sqlite3.Connection, data: dict) -> int:
    ts = db.now()
    cur = conn.execute(
        """INSERT INTO bottle (name, category, origin, abv, flavor, note, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"].strip(),
            data.get("category"),
            data.get("origin"),
            data.get("abv"),
            data.get("flavor"),
            data.get("note"),
            ts,
            ts,
        ),
    )
    bottle_id = int(cur.lastrowid)
    set_tags(conn, bottle_id, data.get("tags") or [])
    return bottle_id


def update_spirit(conn: sqlite3.Connection, bottle_id: int, data: dict) -> None:
    fields = ["name", "category", "origin", "abv", "flavor", "note"]
    sets, args = [], []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            args.append(data[f] if f != "name" else (data[f] or "").strip())
    if "tags" in data:
        set_tags(conn, bottle_id, data["tags"] or [])
    if not sets:
        return
    sets.append("updated_at = ?")
    args.extend([db.now(), bottle_id])
    conn.execute(f"UPDATE bottle SET {', '.join(sets)} WHERE id = ?", args)


def set_tags(conn: sqlite3.Connection, bottle_id: int, names: list[str]) -> None:
    conn.execute("DELETE FROM bottle_tag WHERE bottle_id = ?", (bottle_id,))
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        conn.execute("INSERT OR IGNORE INTO tag (name) VALUES (?)", (name,))
        tag_id = conn.execute("SELECT id FROM tag WHERE name = ?", (name,)).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO bottle_tag (bottle_id, tag_id) VALUES (?, ?)",
            (bottle_id, tag_id),
        )


def spirit_tags(conn: sqlite3.Connection, bottle_id: int) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            """SELECT t.name FROM tag t JOIN bottle_tag bt ON bt.tag_id = t.id
               WHERE bt.bottle_id = ? ORDER BY t.name""",
            (bottle_id,),
        )
    ]


def list_spirits(conn: sqlite3.Connection, scope: str = "stock") -> list[dict]:
    """scope: stock 在库（含待入瓶）/ history 喝完 / all。"""
    cur = conn.execute(
        f"""
        SELECT b.*,
               (SELECT COUNT(*) FROM bottle_lot l
                 WHERE l.bottle_id = b.id AND l.closed_at IS NULL) AS open_lots,
               (SELECT COUNT(*) FROM bottle_lot l WHERE l.bottle_id = b.id) AS all_lots,
               COALESCE((SELECT SUM({BALANCE}) FROM bottle_lot l
                          WHERE l.bottle_id = b.id AND l.closed_at IS NULL), 0) AS balance_ml,
               (SELECT l.price FROM bottle_lot l WHERE l.bottle_id = b.id
                 ORDER BY l.created_at DESC, l.id DESC LIMIT 1) AS last_price,
               (SELECT l.nominal_ml FROM bottle_lot l WHERE l.bottle_id = b.id
                 ORDER BY l.created_at DESC, l.id DESC LIMIT 1) AS last_ml
        FROM bottle b
        ORDER BY b.updated_at DESC
        """
    )
    out = []
    for b in _rows(cur):
        b["in_stock"] = b["open_lots"] > 0
        b["pending"] = b["all_lots"] == 0
        if scope == "stock" and not (b["in_stock"] or b["pending"]):
            continue
        if scope == "history" and (b["in_stock"] or b["pending"]):
            continue
        b["unit_cost"] = (b["last_price"] / b["last_ml"]) if b["last_price"] and b["last_ml"] else None
        b["tags"] = spirit_tags(conn, b["id"])
        out.append(b)
    return out


def get_spirit(conn: sqlite3.Connection, bottle_id: int) -> dict | None:
    bottle = _row(conn.execute("SELECT * FROM bottle WHERE id = ?", (bottle_id,)))
    if not bottle:
        return None
    bottle["tags"] = spirit_tags(conn, bottle_id)
    bottle["lots"] = list_lots(conn, bottle_id)
    bottle["balance_ml"] = sum(l["balance_ml"] for l in bottle["lots"] if not l["closed_at"])
    bottle["in_stock"] = any(not l["closed_at"] for l in bottle["lots"])
    bottle["pending"] = not bottle["lots"]
    priced = [l for l in bottle["lots"] if l.get("price") and l.get("nominal_ml")]
    last = max(priced, key=lambda l: (l.get("created_at") or "", l["id"])) if priced else None
    bottle["unit_cost"] = (last["price"] / last["nominal_ml"]) if last else None
    return bottle


def list_lots(conn: sqlite3.Connection, bottle_id: int) -> list[dict]:
    cur = conn.execute(
        f"""SELECT l.*, {USABLE} AS usable_ml, {BALANCE} AS balance_ml,
                   ROW_NUMBER() OVER (ORDER BY l.created_at, l.id) AS seq
            FROM bottle_lot l WHERE l.bottle_id = ?
            ORDER BY l.closed_at IS NOT NULL, l.opened_on IS NULL, l.created_at""",
        (bottle_id,),
    )
    lots = _rows(cur)
    for l in lots:
        l["unit_cost"] = (l["price"] / l["usable_ml"]) if l["price"] and l["usable_ml"] else None
    return lots


def get_lot(conn: sqlite3.Connection, lot_id: int | None) -> dict | None:
    if not lot_id:
        return None
    lot = _row(
        conn.execute(
            f"""SELECT l.*, {USABLE} AS usable_ml, {BALANCE} AS balance_ml
                FROM bottle_lot l WHERE l.id = ?""",
            (lot_id,),
        )
    )
    if lot:
        lot["unit_cost"] = (lot["price"] / lot["usable_ml"]) if lot["price"] and lot["usable_ml"] else None
    return lot


def add_lot(conn: sqlite3.Connection, bottle_id: int, data: dict) -> int:
    nominal = float(data.get("nominal_ml") or 0)
    if nominal <= 0:
        raise store.Conflict("标称容量要大于 0")
    ts = db.now()
    cur = conn.execute(
        """INSERT INTO bottle_lot (bottle_id, nominal_ml, price, bought_on, opened_on, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            bottle_id,
            nominal,
            data.get("price"),
            data.get("bought_on"),
            data.get("opened_on"),
            data.get("note"),
            ts,
        ),
    )
    lot_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO bottle_stock_event (lot_id, kind, delta_ml, note, at) VALUES (?, 'intake', 0, ?, ?)",
        (lot_id, data.get("note"), ts),
    )
    conn.execute("UPDATE bottle SET updated_at = ? WHERE id = ?", (ts, bottle_id))
    return lot_id


def open_lot(conn: sqlite3.Connection, lot_id: int) -> None:
    lot = get_lot(conn, lot_id)
    if not lot:
        raise store.Conflict("没有这一瓶")
    if lot["closed_at"]:
        raise store.Conflict("这瓶已经关了")
    if lot["opened_on"]:
        raise store.Conflict("这瓶开过了")
    conn.execute(
        "UPDATE bottle_lot SET opened_on = ? WHERE id = ?",
        (db.now()[:10], lot_id),
    )
    conn.execute("UPDATE bottle SET updated_at = ? WHERE id = ?", (db.now(), lot["bottle_id"]))


def adjust_lot(conn: sqlite3.Connection, lot_id: int, actual_ml: float, note: str | None = None) -> dict:
    lot = get_lot(conn, lot_id)
    if not lot:
        raise store.Conflict("没有这一瓶")
    if lot["closed_at"]:
        raise store.Conflict("这瓶已经关了")
    delta = float(actual_ml) - lot["balance_ml"]
    conn.execute(
        "INSERT INTO bottle_stock_event (lot_id, kind, delta_ml, note, at) VALUES (?, 'adjust', ?, ?, ?)",
        (lot_id, delta, note, db.now()),
    )
    conn.execute("UPDATE bottle SET updated_at = ? WHERE id = ?", (db.now(), lot["bottle_id"]))
    after = get_lot(conn, lot_id)
    return {"delta_ml": round(delta, 1), "balance_ml": after["balance_ml"]}


def close_lot(conn: sqlite3.Connection, lot_id: int, note: str | None = None) -> dict:
    lot = get_lot(conn, lot_id)
    if not lot:
        raise store.Conflict("没有这一瓶")
    if lot["closed_at"]:
        raise store.Conflict("这瓶已经关过了")
    balance = lot["balance_ml"]
    ts = db.now()
    conn.execute(
        "INSERT INTO bottle_stock_event (lot_id, kind, delta_ml, note, at) VALUES (?, 'close_lot', ?, ?, ?)",
        (lot_id, -balance, note, ts),
    )
    conn.execute("UPDATE bottle_lot SET closed_at = ? WHERE id = ?", (ts, lot_id))
    conn.execute("UPDATE bottle SET updated_at = ? WHERE id = ?", (ts, lot["bottle_id"]))
    return {"deviation_ml": round(balance, 1), "lot": get_lot(conn, lot_id)}


def record_drink(conn: sqlite3.Connection, data: dict) -> dict:
    """倒一杯。瓶子由人选；毫升是当次实际倒了多少。"""
    lot = get_lot(conn, int(data["lot_id"]))
    if not lot:
        raise store.Conflict("没有这一瓶")
    if lot["closed_at"]:
        raise store.Conflict("这瓶已经关了，换一瓶")

    amount = float(data["amount_ml"])
    if amount <= 0:
        raise store.Conflict("毫升要大于 0")
    if amount > lot["balance_ml"]:
        raise store.Conflict(
            f"这瓶只剩 {lot['balance_ml']:.0f} ml，不够 {amount:g} ml。"
            "换一瓶、改用量，或先盘点"
        )

    person_id = data.get("person_id") or store.ensure_person(conn, data.get("person"))
    ts = data.get("at") or db.now()
    cur = conn.execute(
        """INSERT INTO consumption_event
             (kind, bottle_lot_id, person_id, amount_ml, unit_cost, note, at)
           VALUES ('drink', ?, ?, ?, ?, ?, ?)""",
        (lot["id"], person_id, amount, lot["unit_cost"], data.get("note"), ts),
    )
    conn.execute("UPDATE bottle SET updated_at = ? WHERE id = ?", (db.now(), lot["bottle_id"]))
    if not lot["opened_on"]:
        conn.execute(
            "UPDATE bottle_lot SET opened_on = ? WHERE id = ? AND opened_on IS NULL",
            (ts[:10], lot["id"]),
        )
    after = get_lot(conn, lot["id"])
    bottle = _row(conn.execute("SELECT abv FROM bottle WHERE id = ?", (lot["bottle_id"],)))
    return {
        "id": int(cur.lastrowid),
        "lot_id": lot["id"],
        "amount_ml": amount,
        "cost": (amount * lot["unit_cost"]) if lot["unit_cost"] else None,
        "alcohol_g": alcohol_g(amount, bottle["abv"] if bottle else None),
        "balance_ml": after["balance_ml"],
        "near_empty": after["balance_ml"] < amount,
    }


def void_drink_if_needed(conn: sqlite3.Connection, row: dict, ts: str) -> bool:
    """已关瓶的饮酒撤回：差额记成当天调整。返回是否补了调整。"""
    lot = get_lot(conn, row.get("bottle_lot_id"))
    if lot and lot["closed_at"]:
        conn.execute(
            "INSERT INTO bottle_stock_event (lot_id, kind, delta_ml, note, at) VALUES (?, 'adjust', ?, ?, ?)",
            (lot["id"], -row["amount_ml"], f"撤回已关瓶的一笔 {row['amount_ml']:g} ml", ts),
        )
        return True
    return False
