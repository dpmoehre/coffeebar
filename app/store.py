"""豆子、批次、事件、人的读写。

三条硬口径（见 docs/002）：
1. 账面剩余 = 可用克重 + Σ stock_event.delta_g − Σ 未撤回消耗.amount_g
2. 写消耗时冻结 unit_cost 快照，统计只读快照，历史金额不回溯改写
3. 撤回只写 voided_at，不物理删；已撤回的才能彻底删（库存不再动）；已关袋批次的差额补一笔当天的 adjust
"""

from __future__ import annotations

import json
import sqlite3

from . import db, photos

# 可用克重：开袋实称有则用之，否则用包装标称（刚拆袋不会称，默认走标称）
USABLE = "COALESCE(l.measured_g, l.nominal_g)"

# 账面剩余
BALANCE = f"""
    {USABLE}
    + COALESCE((SELECT SUM(delta_g) FROM stock_event WHERE lot_id = l.id), 0)
    - COALESCE((SELECT SUM(amount_g) FROM consumption_event
                WHERE lot_id = l.id AND voided_at IS NULL), 0)
"""

# 克价 = 买入价 ÷ 可用克重。豆库一张卡可能挂多袋，按还剩的克加权；
# 在库空了（历史）就退回最近一袋买入时的克价，方便还按价钱翻旧豆。
REMAINING_VALUE = f"""
    (SELECT SUM(({BALANCE}) * (l.price / NULLIF({USABLE}, 0)))
       FROM bean_lot l
      WHERE l.bean_id = b.id AND l.closed_at IS NULL
        AND l.price IS NOT NULL AND {USABLE} > 0 AND ({BALANCE}) > 0)
"""
PRICED_G = f"""
    (SELECT SUM({BALANCE})
       FROM bean_lot l
      WHERE l.bean_id = b.id AND l.closed_at IS NULL
        AND l.price IS NOT NULL AND {USABLE} > 0 AND ({BALANCE}) > 0)
"""
LAST_UNIT_COST = f"""
    (SELECT l.price / NULLIF({USABLE}, 0)
       FROM bean_lot l
      WHERE l.bean_id = b.id AND l.price IS NOT NULL AND {USABLE} > 0
      ORDER BY l.created_at DESC, l.id DESC LIMIT 1)
"""


def unit_cost_of(lots: list[dict]) -> float | None:
    """一支豆的克价：在库按剩余加权，否则用最近一袋的买入克价。"""
    open_priced = [
        l for l in lots
        if not l.get("closed_at")
        and l.get("price")
        and l.get("usable_g")
        and (l.get("balance_g") or 0) > 0
    ]
    if open_priced:
        grams = sum(l["balance_g"] for l in open_priced)
        value = sum(l["balance_g"] * (l["price"] / l["usable_g"]) for l in open_priced)
        return value / grams if grams else None
    priced = [l for l in lots if l.get("price") and l.get("usable_g")]
    if not priced:
        return None
    last = max(priced, key=lambda l: (l.get("created_at") or "", l["id"]))
    return last["price"] / last["usable_g"]


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
        """INSERT INTO bean (name, origin, varietal, producer, altitude, process, roast,
                             water_temp, note, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"].strip(),
            data.get("origin"),
            data.get("varietal"),
            data.get("producer"),
            data.get("altitude"),
            data.get("process"),
            data.get("roast"),
            data.get("water_temp"),
            data.get("note"),
            ts,
            ts,
        ),
    )
    bean_id = int(cur.lastrowid)
    # 店家豆卡上有推荐参数就直接存成这支豆的默认，省得每次重填
    conn.execute(
        "INSERT INTO brew_guide (bean_id, method, dose_g, ratio, note) VALUES (?, ?, ?, ?, ?)",
        (
            bean_id,
            data.get("brew_method") or "v60",
            float(data.get("brew_dose_g") or 15),
            float(data.get("brew_ratio") or 16),
            data.get("brew_note"),
        ),
    )
    set_tags(conn, bean_id, data.get("tags") or [])
    return bean_id


def update_bean(conn: sqlite3.Connection, bean_id: int, data: dict) -> None:
    fields = [
        "name", "origin", "varietal", "producer", "altitude",
        "process", "roast", "water_temp", "note",
    ]
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
    """scope: stock 在库（含只建了豆卡还没入袋的）/ history 历史（曾有袋且全关）/ all 全部。

    只建豆卡没入袋的豆子一袋都没有，既不算在库也不算喝完了。它跟着「在库」出，
    标成待入袋——否则刚建的豆卡会直接掉进历史里找不着。
    """
    cur = conn.execute(
        f"""
        SELECT b.*,
               (SELECT COUNT(*) FROM bean_lot l
                 WHERE l.bean_id = b.id AND l.closed_at IS NULL) AS open_lots,
               (SELECT COUNT(*) FROM bean_lot l WHERE l.bean_id = b.id) AS all_lots,
               COALESCE((SELECT SUM({BALANCE}) FROM bean_lot l
                          WHERE l.bean_id = b.id AND l.closed_at IS NULL), 0) AS balance_g,
               COALESCE((SELECT SUM({USABLE}) FROM bean_lot l
                          WHERE l.bean_id = b.id AND l.closed_at IS NULL), 0) AS usable_g,
               {REMAINING_VALUE} AS remaining_value,
               {PRICED_G} AS priced_g,
               {LAST_UNIT_COST} AS last_unit_cost
        FROM bean b
        ORDER BY b.updated_at DESC
        """
    )
    beans = _rows(cur)
    out = []
    for b in beans:
        b["in_stock"] = b["open_lots"] > 0
        b["pending"] = b["all_lots"] == 0  # 豆卡建好了，还没称重入袋
        if scope == "stock" and not (b["in_stock"] or b["pending"]):
            continue
        if scope == "history" and (b["in_stock"] or b["pending"]):
            continue
        if b["priced_g"]:
            b["unit_cost"] = b["remaining_value"] / b["priced_g"]
        else:
            b["unit_cost"] = b["last_unit_cost"]
        del b["remaining_value"], b["priced_g"], b["last_unit_cost"]
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
    bean["pending"] = not bean["lots"]
    bean["unit_cost"] = unit_cost_of(bean["lots"])
    bean["scores"] = latest_score(conn, bean_id)
    bean["brew"] = _row(
        conn.execute(
            "SELECT method, dose_g, ratio, note FROM brew_guide WHERE bean_id = ?", (bean_id,)
        )
    ) or {"method": "v60", "dose_g": 15, "ratio": 16, "note": None}
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


def set_brew_default(
    conn: sqlite3.Connection,
    bean_id: int,
    method: str,
    dose_g: float,
    ratio: float,
    note: str | None = None,
) -> None:
    """只存默认值，方便下次不重填；方案本身每次按当场输入算。"""
    conn.execute(
        """INSERT INTO brew_guide (bean_id, method, dose_g, ratio, note) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(bean_id) DO UPDATE
             SET method = ?, dose_g = ?, ratio = ?, note = COALESCE(?, note)""",
        (bean_id, method, dose_g, ratio, note, method, dose_g, ratio, note),
    )


# ── 批次（袋子） ────────────────────────────────────────────


def list_lots(conn: sqlite3.Connection, bean_id: int) -> list[dict]:
    # seq 按买入顺序编号（第 1 袋、第 2 袋）。同一支豆两袋规格价钱可能一模一样，
    # 没有编号就分不清谁是谁。它不跟显示顺序走——开封会把袋子提到前面，
    # 但「第 2 袋」得一直是第 2 袋。
    cur = conn.execute(
        f"""SELECT l.*, {USABLE} AS usable_g, {BALANCE} AS balance_g,
                   ROW_NUMBER() OVER (ORDER BY l.created_at, l.id) AS seq,
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


def open_lot(conn: sqlite3.Connection, lot_id: int, on: str | None = None) -> dict:
    """开封这一袋。只记日子，不动克数——撕开袋子并没有让豆子变少。

    第一次冲煮时也会自动补上开封日，这里是显式的那条路（配开封动画）。
    """
    lot = get_lot(conn, lot_id)
    if not lot:
        raise Conflict("没有这一袋")
    if lot["closed_at"]:
        raise Conflict("这袋已经关了")
    if lot["opened_on"]:
        raise Conflict(f"这袋 {lot['opened_on']} 就开过了")
    day = on or db.now()[:10]
    conn.execute("UPDATE bean_lot SET opened_on = ? WHERE id = ?", (day, lot_id))
    conn.execute("UPDATE bean SET updated_at = ? WHERE id = ?", (db.now(), lot["bean_id"]))
    return get_lot(conn, lot_id)


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
    """带上每人的记录条数，删人前要拿它提示影响面。"""
    where = "" if include_inactive else " WHERE p.active = 1"
    return _rows(
        conn.execute(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM consumption_event c
                         WHERE c.person_id = p.id AND c.voided_at IS NULL) AS cups
                FROM person p{where} ORDER BY p.active DESC, p.name"""
        )
    )


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
    """停用是轻量选项：选人列表里不再出现，名字和归属都还在。"""
    conn.execute("UPDATE person SET active = ? WHERE id = ?", (1 if active else 0, person_id))


def delete_person(conn: sqlite3.Connection, person_id: int) -> dict:
    """真删掉这个人。

    他名下的流水**不删**，只是失去归属变成「没记」——那些克重是真扣过的，
    钱也真花了，删人不该让库存账和统计总数跟着变。想把记录留给别人，先用
    「改归属」挪走再删。
    """
    row = _row(conn.execute("SELECT * FROM person WHERE id = ?", (person_id,)))
    if not row:
        raise Conflict("没有这个人")

    affected = conn.execute(
        "SELECT COUNT(*) FROM consumption_event WHERE person_id = ?", (person_id,)
    ).fetchone()[0]

    ts = db.now()
    if affected:
        conn.executemany(
            """INSERT INTO consumption_audit (cons_id, field, old_value, new_value, at)
               VALUES (?, 'person', ?, NULL, ?)""",
            [
                (r[0], row["name"], ts)
                for r in conn.execute(
                    "SELECT id FROM consumption_event WHERE person_id = ?", (person_id,)
                ).fetchall()
            ],
        )
        conn.execute(
            "UPDATE consumption_event SET person_id = NULL WHERE person_id = ?", (person_id,)
        )
    conn.execute("DELETE FROM person WHERE id = ?", (person_id,))
    return {"name": row["name"], "orphaned": affected}


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
    as_cup = 0 if data.get("as_cup") in (0, False, "0") else 1

    cur = conn.execute(
        """INSERT INTO consumption_event
             (kind, lot_id, person_id, amount_g, unit_cost, brew_method, brew_ratio,
              brew_total_s, brew_stages, note, as_cup, at)
           VALUES ('coffee', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            as_cup,
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
        "as_cup": as_cup,
        "balance_g": after["balance_g"],
        "near_empty": after["balance_g"] < amount,
    }


def record_writeoff(conn: sqlite3.Connection, lot_id: int, note: str | None = None) -> dict:
    """整袋补录：克重和钱进统计，不算一杯、不算到人。已关袋只要账面还在也能写。"""
    lot = get_lot(conn, lot_id)
    if not lot:
        raise Conflict("没有这一袋")
    amount = lot["balance_g"]
    if amount <= 0:
        raise Conflict("这袋账面已经是 0，没有可补录的克重")
    already = conn.execute(
        """SELECT id FROM consumption_event
           WHERE lot_id = ? AND as_cup = 0 AND voided_at IS NULL""",
        (lot_id,),
    ).fetchone()
    if already:
        raise Conflict("这袋已经补录过整袋消耗")
    closed = lot["closed_at"]
    if closed:
        conn.execute("UPDATE bean_lot SET closed_at = NULL WHERE id = ?", (lot_id,))
    try:
        return record_brew(
            conn,
            {
                "lot_id": lot_id,
                "amount_g": amount,
                "as_cup": 0,
                "note": note or "补录：已喝光，克重和钱进统计，不算到人",
            },
        )
    finally:
        if closed:
            conn.execute("UPDATE bean_lot SET closed_at = ? WHERE id = ?", (closed, lot_id))


def retarget_finished_lot(
    conn: sqlite3.Connection, lot_id: int, nominal_g: float, price: float, note: str | None = None
) -> dict:
    """改已关袋的标称和价钱，清掉关袋偏差，再按新克重整袋补录。"""
    lot = get_lot(conn, lot_id)
    if not lot:
        raise Conflict("没有这一袋")
    conn.execute(
        "UPDATE bean_lot SET nominal_g = ?, price = ? WHERE id = ?",
        (float(nominal_g), float(price), lot_id),
    )
    conn.execute(
        "UPDATE stock_event SET delta_g = 0, note = ? WHERE lot_id = ? AND kind = 'close_lot'",
        ("关袋（整袋消耗已另记）", lot_id),
    )
    conn.execute(
        "UPDATE stock_event SET note = ? WHERE lot_id = ? AND kind = 'intake'",
        (f"入库 标称 {float(nominal_g):g} g", lot_id),
    )
    closed = lot["closed_at"]
    if closed:
        conn.execute("UPDATE bean_lot SET closed_at = NULL WHERE id = ?", (lot_id,))
    out = record_writeoff(conn, lot_id, note)
    if closed:
        close_lot(conn, lot_id, "关袋（整袋消耗已另记）")
    return out


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

    compensated = False
    if row["kind"] == "drink":
        from . import spirits as spirits_mod

        compensated = spirits_mod.void_drink_if_needed(conn, row, ts)
    else:
        lot = get_lot(conn, row["lot_id"])
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
    if row["kind"] == "drink":
        from . import spirits as spirits_mod

        lot = spirits_mod.get_lot(conn, row["bottle_lot_id"])
        if lot and not lot["closed_at"] and row["amount_ml"] > lot["balance_ml"]:
            raise Conflict("恢复后账面会变成负数，先盘点")
    else:
        lot = get_lot(conn, row["lot_id"])
        if lot and not lot["closed_at"] and row["amount_g"] > lot["balance_g"]:
            raise Conflict("恢复后账面会变成负数，先盘点补重")
    conn.execute(
        "UPDATE consumption_event SET voided_at = NULL, void_reason = NULL WHERE id = ?",
        (cons_id,),
    )


def delete_voided_consumption(conn: sqlite3.Connection, cons_id: int) -> dict:
    """彻底删掉已经撤回的一笔。库存在撤回时已经加回去，这里不再动账。"""
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    if not row["voided_at"]:
        raise Conflict("先撤回再删。没撤回的记录还在账上，不能直接抹掉")
    n = photos.purge_consumption_photos(conn, cons_id)
    conn.execute("DELETE FROM consumption_event WHERE id = ?", (cons_id,))
    return {"ok": True, "id": cons_id, "photos_removed": n}


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
    bottle_id: int | None = None,
    person_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """明细含已撤回的行（界面上划掉显示），汇总统计一律排除。"""
    where, args = ["1 = 1"], []
    if bean_id:
        where.append("l.bean_id = ?")
        args.append(bean_id)
    if bottle_id:
        where.append("bl.bottle_id = ?")
        args.append(bottle_id)
    if person_id:
        where.append("c.person_id = ?")
        args.append(person_id)
    cur = conn.execute(
        f"""SELECT c.*, b.name AS bean_name, p.name AS person_name,
                   l.nominal_g, l.bought_on, l.closed_at AS lot_closed_at, s.seq AS lot_seq,
                   sp.name AS spirit_name, bl.nominal_ml, bl.closed_at AS bottle_closed_at,
                   CASE c.kind
                     WHEN 'drink' THEN (c.amount_ml * COALESCE(c.unit_cost, 0))
                     ELSE (c.amount_g * COALESCE(c.unit_cost, 0))
                   END AS cost
            FROM consumption_event c
            LEFT JOIN bean_lot l ON l.id = c.lot_id
            LEFT JOIN bean b ON b.id = l.bean_id
            LEFT JOIN bottle_lot bl ON bl.id = c.bottle_lot_id
            LEFT JOIN bottle sp ON sp.id = bl.bottle_id
            LEFT JOIN person p ON p.id = c.person_id
            -- 和 list_lots 一样按买入顺序编号，日志里才说得清是哪一袋
            LEFT JOIN (SELECT id, ROW_NUMBER() OVER
                                (PARTITION BY bean_id ORDER BY created_at, id) AS seq
                         FROM bean_lot) s ON s.id = l.id
            WHERE {' AND '.join(where)}
            ORDER BY c.at DESC, c.id DESC LIMIT ?""",
        (*args, limit),
    )
    out = _rows(cur)
    for row in out:
        raw = row.get("brew_stages")
        if isinstance(raw, str) and raw:
            try:
                row["brew_stages"] = json.loads(raw)
            except ValueError:
                pass
    by_photo = photos.list_consumption_photos(conn, [r["id"] for r in out])
    for row in out:
        row["photos"] = by_photo.get(row["id"], [])
    return out
