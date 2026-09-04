"""豆子、批次、事件、人的读写。

三条硬口径（见 docs/002）：
1. 账面剩余 = 可用克重 + Σ stock_event.delta_g − Σ 未撤回消耗.amount_g
2. 写消耗时冻结 unit_cost 快照，统计只读快照，历史金额不回溯改写
3. 撤回只写 voided_at，不物理删；已关袋批次的差额补一笔当天的 adjust
"""

from __future__ import annotations

import json
import sqlite3

from . import db

# 可用克重：开袋实称有则用之，否则用包装标称（刚拆袋不会称，默认走标称）
USABLE = "COALESCE(l.measured_g, l.nominal_g)"

# 账面剩余
BALANCE = f"""
    {USABLE}
    + COALESCE((SELECT SUM(delta_g) FROM stock_event WHERE lot_id = l.id), 0)
    - COALESCE((SELECT SUM(amount_g) FROM consumption_event
                WHERE lot_id = l.id AND voided_at IS NULL), 0)
"""


class Conflict(Exception):
    """业务上不该继续的情况，路由层转成 409。"""


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _row(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


# ── 豆子 ────────────────────────────────────────────────────


def create_bean(conn: sqlite3.Connection, data: dict) -> int:
    ts = db.now()
    cur = conn.execute(
        """INSERT INTO bean (name, origin, process, roast, water_temp, note,
                             created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"].strip(),
            data.get("origin"),
            data.get("process"),
            data.get("roast"),
            data.get("water_temp"),
            data.get("note"),
            ts,
            ts,
        ),
    )
    bean_id = int(cur.lastrowid)
    conn.execute("INSERT INTO brew_guide (bean_id) VALUES (?)", (bean_id,))
    set_tags(conn, bean_id, data.get("tags") or [])
    return bean_id


def update_bean(conn: sqlite3.Connection, bean_id: int, data: dict) -> None:
    fields = ["name", "origin", "process", "roast", "water_temp", "note"]
    sets, vals = [], []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            vals.append(data[f])
    if sets:
        sets.append("updated_at = ?")
        vals.extend([db.now(), bean_id])
        conn.execute(f"UPDATE bean SET {', '.join(sets)} WHERE id = ?", vals)
    if "tags" in data:
        set_tags(conn, bean_id, data["tags"] or [])


def set_tags(conn: sqlite3.Connection, bean_id: int, names: list[str]) -> None:
    """自由标签：输入即创建，没有标签后台。"""
    conn.execute("DELETE FROM bean_tag WHERE bean_id = ?", (bean_id,))
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        conn.execute("INSERT OR IGNORE INTO tag (name) VALUES (?)", (name,))
        tag_id = conn.execute("SELECT id FROM tag WHERE name = ?", (name,)).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO bean_tag (bean_id, tag_id) VALUES (?, ?)",
            (bean_id, tag_id),
        )


def bean_tags(conn: sqlite3.Connection, bean_id: int) -> list[str]:
    cur = conn.execute(
        """SELECT t.name FROM tag t JOIN bean_tag bt ON bt.tag_id = t.id
           WHERE bt.bean_id = ? ORDER BY t.name""",
        (bean_id,),
    )
    return [r[0] for r in cur.fetchall()]


def list_beans(conn: sqlite3.Connection, scope: str = "stock") -> list[dict]:
    """scope: stock 在库 / history 历史（所有袋都关了）/ all 全部。"""
    cur = conn.execute(
        f"""
        SELECT b.*,
               (SELECT COUNT(*) FROM bean_lot l
                 WHERE l.bean_id = b.id AND l.closed_at IS NULL) AS open_lots,
               (SELECT COUNT(*) FROM bean_lot l WHERE l.bean_id = b.id) AS all_lots,
               COALESCE((SELECT SUM({BALANCE}) FROM bean_lot l
                          WHERE l.bean_id = b.id AND l.closed_at IS NULL), 0) AS balance_g,
               COALESCE((SELECT SUM({USABLE}) FROM bean_lot l
                          WHERE l.bean_id = b.id AND l.closed_at IS NULL), 0) AS usable_g
        FROM bean b
        ORDER BY b.updated_at DESC
        """
    )
    beans = _rows(cur)
    out = []
    for b in beans:
        b["in_stock"] = b["open_lots"] > 0
        if scope == "stock" and not b["in_stock"]:
            continue
        if scope == "history" and b["in_stock"]:
            continue
        b["tags"] = bean_tags(conn, b["id"])
        b["scores"] = latest_score(conn, b["id"])
        out.append(b)
    return out


def get_bean(conn: sqlite3.Connection, bean_id: int) -> dict | None:
    bean = _row(conn.execute("SELECT * FROM bean WHERE id = ?", (bean_id,)))
    if not bean:
        return None
    bean["tags"] = bean_tags(conn, bean_id)
    bean["lots"] = list_lots(conn, bean_id)
    bean["balance_g"] = sum(l["balance_g"] for l in bean["lots"] if not l["closed_at"])
    bean["in_stock"] = any(not l["closed_at"] for l in bean["lots"])
    bean["scores"] = latest_score(conn, bean_id)
    bean["brew"] = _row(
        conn.execute("SELECT method, dose_g, ratio FROM brew_guide WHERE bean_id = ?", (bean_id,))
    ) or {"method": "v60", "dose_g": 15, "ratio": 16}
    return bean


def latest_score(conn: sqlite3.Connection, bean_id: int) -> dict | None:
    return _row(
        conn.execute(
            "SELECT * FROM bean_score WHERE bean_id = ? ORDER BY at DESC LIMIT 1",
            (bean_id,),
        )
    )


def add_score(conn: sqlite3.Connection, bean_id: int, data: dict) -> int:
    cols = ["dry", "flavor", "aftertaste", "acidity", "sweetness", "body", "balance", "overall"]
    cur = conn.execute(
        f"""INSERT INTO bean_score (bean_id, {', '.join(cols)}, comment, at)
            VALUES (?, {', '.join('?' * len(cols))}, ?, ?)""",
        (bean_id, *[data.get(c) for c in cols], data.get("comment"), db.now()),
    )
    return int(cur.lastrowid)


def set_brew_default(conn: sqlite3.Connection, bean_id: int, method: str, dose_g: float, ratio: float) -> None:
    """只存默认值，方便下次不重填；方案本身每次按当场输入算。"""
    conn.execute(
        """INSERT INTO brew_guide (bean_id, method, dose_g, ratio) VALUES (?, ?, ?, ?)
           ON CONFLICT(bean_id) DO UPDATE SET method = ?, dose_g = ?, ratio = ?""",
        (bean_id, method, dose_g, ratio, method, dose_g, ratio),
    )


# ── 批次（袋子） ────────────────────────────────────────────


def list_lots(conn: sqlite3.Connection, bean_id: int) -> list[dict]:
    cur = conn.execute(
        f"""SELECT l.*, {USABLE} AS usable_g, {BALANCE} AS balance_g,
                   (SELECT COALESCE(SUM(amount_g), 0) FROM consumption_event
                     WHERE lot_id = l.id AND voided_at IS NULL) AS used_g
            FROM bean_lot l WHERE l.bean_id = ?
            ORDER BY l.closed_at IS NOT NULL, l.opened_on IS NULL, l.created_at""",
        (bean_id,),
    )
    lots = _rows(cur)
    for l in lots:
        l["unit_cost"] = (l["price"] / l["usable_g"]) if l["price"] and l["usable_g"] else None
    return lots


def get_lot(conn: sqlite3.Connection, lot_id: int) -> dict | None:
    lot = _row(
        conn.execute(
            f"""SELECT l.*, {USABLE} AS usable_g, {BALANCE} AS balance_g
                FROM bean_lot l WHERE l.id = ?""",
            (lot_id,),
        )
    )
    if lot:
        lot["unit_cost"] = (lot["price"] / lot["usable_g"]) if lot["price"] and lot["usable_g"] else None
    return lot


def add_lot(conn: sqlite3.Connection, bean_id: int, data: dict) -> int:
    """再入一袋：只加批次，不新建豆卡。标称必填，实称通常为空。"""
    nominal = float(data["nominal_g"])
    if nominal <= 0:
        raise Conflict("包装标称克重要大于 0")
    ts = db.now()
    cur = conn.execute(
        """INSERT INTO bean_lot (bean_id, nominal_g, measured_g, price, bought_on,
                                 opened_on, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            bean_id,
            nominal,
            data.get("measured_g"),
            data.get("price"),
            data.get("bought_on"),
            data.get("opened_on"),
            data.get("note"),
            ts,
        ),
    )
    lot_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO stock_event (lot_id, kind, delta_g, note, at) VALUES (?, 'intake', 0, ?, ?)",
        (lot_id, f"入库 标称 {nominal:g} g", ts),
    )
    conn.execute("UPDATE bean SET updated_at = ? WHERE id = ?", (ts, bean_id))
    return lot_id


def set_measured(conn: sqlite3.Connection, lot_id: int, measured_g: float) -> None:
    """开袋实称（可选）。改的是「这袋原本有多少」，中途盘点请用 adjust。"""
    lot = get_lot(conn, lot_id)
    if not lot:
        raise Conflict("没有这一袋")
    if lot["closed_at"]:
        raise Conflict("这袋已经关了，不能再改实称")
    before = lot["usable_g"]
    conn.execute("UPDATE bean_lot SET measured_g = ? WHERE id = ?", (measured_g, lot_id))
    conn.execute(
        "INSERT INTO stock_event (lot_id, kind, delta_g, note, at) VALUES (?, 'measure', 0, ?, ?)",
        (lot_id, f"开袋实称 {before:g} → {measured_g:g} g", db.now()),
    )


def adjust_lot(conn: sqlite3.Connection, lot_id: int, actual_g: float, note: str | None = None) -> float:
    """中途盘点：人输入现在实际还剩多少，系统记下与账面的差。"""
    lot = get_lot(conn, lot_id)
    if not lot:
        raise Conflict("没有这一袋")
    if lot["closed_at"]:
        raise Conflict("这袋已经关了")
    delta = float(actual_g) - lot["balance_g"]
    conn.execute(
        "INSERT INTO stock_event (lot_id, kind, delta_g, note, at) VALUES (?, 'adjust', ?, ?, ?)",
        (lot_id, delta, note or f"盘点到 {actual_g:g} g", db.now()),
    )
    return delta


def close_lot(conn: sqlite3.Connection, lot_id: int, note: str | None = None) -> float:
    """这袋用完：人确认才关，账面余数记成偏差结清。返回偏差克重。"""
    lot = get_lot(conn, lot_id)
    if not lot:
        raise Conflict("没有这一袋")
    if lot["closed_at"]:
        raise Conflict("这袋已经关过了")
    balance = lot["balance_g"]
    ts = db.now()
    conn.execute(
        "INSERT INTO stock_event (lot_id, kind, delta_g, note, at) VALUES (?, 'close_lot', ?, ?, ?)",
        (lot_id, -balance, note or f"关袋结清偏差 {balance:+.1f} g", ts),
    )
    conn.execute("UPDATE bean_lot SET closed_at = ? WHERE id = ?", (ts, lot_id))
    return balance


# ── 人（谁喝的） ────────────────────────────────────────────


def list_people(conn: sqlite3.Connection, include_inactive: bool = False) -> list[dict]:
    sql = "SELECT * FROM person"
    if not include_inactive:
        sql += " WHERE active = 1"
    return _rows(conn.execute(sql + " ORDER BY active DESC, name"))


def ensure_person(conn: sqlite3.Connection, name: str | None) -> int | None:
    """输入即创建。名字为空表示不记是谁。"""
    if not name or not name.strip():
        return None
    name = name.strip()
    conn.execute(
        "INSERT INTO person (name, created_at) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
        (name, db.now()),
    )
    return int(conn.execute("SELECT id FROM person WHERE name = ?", (name,)).fetchone()[0])


def rename_person(conn: sqlite3.Connection, person_id: int, name: str) -> None:
    """改名只改这一行；历史流水通过外键自动跟着变。"""
    name = name.strip()
    if not name:
        raise Conflict("名字不能为空")
    exists = conn.execute(
        "SELECT id FROM person WHERE name = ? AND id <> ?", (name, person_id)
    ).fetchone()
    if exists:
        raise Conflict(f"已经有叫「{name}」的人了")
    conn.execute("UPDATE person SET name = ? WHERE id = ?", (name, person_id))


def set_person_active(conn: sqlite3.Connection, person_id: int, active: bool) -> None:
    """停用不是删除：选人列表里不再出现，历史记录仍完整。"""
    conn.execute("UPDATE person SET active = ? WHERE id = ?", (1 if active else 0, person_id))


# ── 冲一次 / 撤回 ───────────────────────────────────────────


def record_brew(conn: sqlite3.Connection, data: dict) -> dict:
    """记一次冲煮。袋子由调用方（人）指定；粉量是当次实际用量。"""
    lot = get_lot(conn, int(data["lot_id"]))
    if not lot:
        raise Conflict("没有这一袋")
    if lot["closed_at"]:
        raise Conflict("这袋已经关了，换一袋")

    amount = float(data["amount_g"])
    if amount <= 0:
        raise Conflict("粉量要大于 0")
    if amount > lot["balance_g"]:
        raise Conflict(
            f"这袋只剩 {lot['balance_g']:.0f} g，不够 {amount:g} g。"
            "换一袋、改粉量，或先盘点补重"
        )

    person_id = data.get("person_id") or ensure_person(conn, data.get("person"))
    ts = data.get("at") or db.now()
    stages = data.get("brew_stages")

    cur = conn.execute(
        """INSERT INTO consumption_event
             (kind, lot_id, person_id, amount_g, unit_cost, brew_method, brew_ratio,
              brew_total_s, brew_stages, note, at)
           VALUES ('coffee', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            lot["id"],
            person_id,
            amount,
            lot["unit_cost"],  # 冻结当时单价，之后改实称/关袋都不影响这一行
            data.get("brew_method"),
            data.get("brew_ratio"),
            data.get("brew_total_s"),
            json.dumps(stages, ensure_ascii=False) if stages else None,
            data.get("note"),
            ts,
        ),
    )
    conn.execute("UPDATE bean SET updated_at = ? WHERE id = ?", (db.now(), lot["bean_id"]))

    # 第一次消耗顺便记开封日
    if not lot["opened_on"]:
        conn.execute(
            "UPDATE bean_lot SET opened_on = ? WHERE id = ? AND opened_on IS NULL",
            (ts[:10], lot["id"]),
        )

    after = get_lot(conn, lot["id"])
    return {
        "id": int(cur.lastrowid),
        "lot_id": lot["id"],
        "amount_g": amount,
        "cost": (amount * lot["unit_cost"]) if lot["unit_cost"] else None,
        "balance_g": after["balance_g"],
        "near_empty": after["balance_g"] < amount,
    }


def void_consumption(conn: sqlite3.Connection, cons_id: int, reason: str | None = None) -> dict:
    """撤回一笔：只划掉不删。已关袋的批次补一笔当天调整，不改写历史。"""
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    if row["voided_at"]:
        raise Conflict("这条已经撤回过了")

    ts = db.now()
    conn.execute(
        "UPDATE consumption_event SET voided_at = ?, void_reason = ? WHERE id = ?",
        (ts, reason, cons_id),
    )

    lot = get_lot(conn, row["lot_id"])
    compensated = False
    if lot and lot["closed_at"]:
        # 那袋已经结清过偏差，别去改过去；差额落在今天
        conn.execute(
            "INSERT INTO stock_event (lot_id, kind, delta_g, note, at) VALUES (?, 'adjust', ?, ?, ?)",
            (lot["id"], -row["amount_g"], f"撤回已关袋的一笔 {row['amount_g']:g} g", ts),
        )
        compensated = True

    return {"id": cons_id, "voided_at": ts, "closed_lot_adjusted": compensated}


def unvoid_consumption(conn: sqlite3.Connection, cons_id: int) -> None:
    """撤回撤错了，恢复这一笔。"""
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    if not row["voided_at"]:
        raise Conflict("这条没有被撤回")
    lot = get_lot(conn, row["lot_id"])
    if lot and not lot["closed_at"] and row["amount_g"] > lot["balance_g"]:
        raise Conflict("恢复后账面会变成负数，先盘点补重")
    conn.execute(
        "UPDATE consumption_event SET voided_at = NULL, void_reason = NULL WHERE id = ?",
        (cons_id,),
    )


def reassign_person(conn: sqlite3.Connection, cons_id: int, person: str | None) -> None:
    """人选错了：只改归属，克重不动，库存不变；留痕。"""
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    old = None
    if row["person_id"]:
        r = conn.execute("SELECT name FROM person WHERE id = ?", (row["person_id"],)).fetchone()
        old = r[0] if r else None
    new_id = ensure_person(conn, person)
    conn.execute("UPDATE consumption_event SET person_id = ? WHERE id = ?", (new_id, cons_id))
    conn.execute(
        """INSERT INTO consumption_audit (cons_id, field, old_value, new_value, at)
           VALUES (?, 'person', ?, ?, ?)""",
        (cons_id, old, (person or "").strip() or None, db.now()),
    )


def list_consumption(
    conn: sqlite3.Connection,
    bean_id: int | None = None,
    person_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """明细含已撤回的行（界面上划掉显示），汇总统计一律排除。"""
    where, args = ["1 = 1"], []
    if bean_id:
        where.append("l.bean_id = ?")
        args.append(bean_id)
    if person_id:
        where.append("c.person_id = ?")
        args.append(person_id)
    cur = conn.execute(
        f"""SELECT c.*, b.name AS bean_name, p.name AS person_name,
                   l.nominal_g, l.bought_on, l.closed_at AS lot_closed_at,
                   (c.amount_g * COALESCE(c.unit_cost, 0)) AS cost
            FROM consumption_event c
            JOIN bean_lot l ON l.id = c.lot_id
            JOIN bean b ON b.id = l.bean_id
            LEFT JOIN person p ON p.id = c.person_id
            WHERE {' AND '.join(where)}
            ORDER BY c.at DESC, c.id DESC LIMIT ?""",
        (*args, limit),
    )
    return _rows(cur)
