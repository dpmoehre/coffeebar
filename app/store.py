"""豆子、批次、事件、人的读写。

三条硬口径（见 docs/002）：
1. 账面剩余 = 可用克重 + Σ stock_event.delta_g − Σ 未撤回消耗.amount_g
2. 写消耗时冻结 unit_cost 快照，统计只读快照，历史金额不回溯改写
3. 撤回只写 voided_at，不物理删；已撤回的才能彻底删（库存不再动）；已关袋批次的差额补一笔当天的 adjust
"""

from __future__ import annotations

import json
import sqlite3

from . import brew, db, photos, places

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

    def __init__(self, message: str, extra: dict | None = None):
        super().__init__(message)
        self.extra = extra or {}


IDENTITY_FIELDS = ("name", "origin", "varietal", "producer", "altitude", "process", "roast")
SCORE_PUBLIC_KEYS = (
    "dry",
    "flavor",
    "aftertaste",
    "acidity",
    "sweetness",
    "body",
    "balance",
    "overall",
    "comment",
    "at",
)


def parse_visibility(value) -> str:
    vis = (value or "private").strip()
    if vis not in ("private", "public"):
        raise Conflict("公开状态只能是 private 或 public")
    return vis


def clear_certification(conn: sqlite3.Connection, bean_id: int) -> None:
    """改了认证相关字段或收回公开后，认证作废，要重新审。"""
    conn.execute(
        """UPDATE bean
              SET certified_at = NULL,
                  certified_by = NULL,
                  places_verified_at = NULL,
                  updated_at = ?
            WHERE id = ?""",
        (db.now(), bean_id),
    )


def _annotate_bean(bean: dict) -> dict:
    bean["visibility"] = bean.get("visibility") or "private"
    bean["certified"] = bool(bean.get("certified_at"))
    return bean


def _public_score(score: dict | None) -> dict | None:
    if not score:
        return None
    return {k: score.get(k) for k in SCORE_PUBLIC_KEYS}


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _row(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


# ── 豆子 ────────────────────────────────────────────────────


def starter_enabled() -> bool:
    import os

    raw = (os.environ.get("COFFEEBAR_STARTER_BEAN") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def give_starter_bean(conn: sqlite3.Connection, owner_id: int) -> int:
    """空库进门的那一支耶加雪菲。标 seed，不算真库存号。"""
    bean_id = create_bean(
        conn,
        {
            "owner_id": owner_id,
            "name": "耶加雪菲",
            "origin": "埃塞俄比亚 耶加雪菲",
            "process": "水洗",
            "roast": "浅烘",
            "water_temp": 92,
            "note": "进门练手用的一支。不是吧台库存，冲完、改掉、删掉都行。",
            "tags": ["入门", "水洗", "柑橘"],
            "brew_method": "v60",
            "brew_dose_g": 15,
            "brew_ratio": 16,
            "brew_note": "中细研磨，闷蒸后分三段。",
        },
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bean)")}
    if "seed" in cols:
        conn.execute("UPDATE bean SET seed = 1 WHERE id = ?", (bean_id,))
    add_lot(conn, bean_id, {"nominal_g": 100, "note": "练习袋"})
    return bean_id



def create_bean(conn: sqlite3.Connection, data: dict) -> int:
    vis = parse_visibility(data["visibility"]) if "visibility" in data else "private"
    ts = db.now()
    cur = conn.execute(
        """INSERT INTO bean (owner_id, name, origin, varietal, producer, altitude, process, roast,
                             water_temp, note, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("owner_id"),
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
    places.sync_gazetteer(conn, bean_id, data.get("origin"), data.get("producer"))
    if vis != "private":
        conn.execute("UPDATE bean SET visibility = ? WHERE id = ?", (vis, bean_id))
    return bean_id


def update_bean(conn: sqlite3.Connection, bean_id: int, data: dict) -> None:
    before = _row(conn.execute("SELECT * FROM bean WHERE id = ?", (bean_id,)))
    if not before:
        raise Conflict("没有这支豆")
    fields = [
        "name", "origin", "varietal", "producer", "altitude",
        "process", "roast", "water_temp", "note",
    ]
    sets, vals = [], []
    identity_changed = False
    for f in fields:
        if f not in data:
            continue
        sets.append(f"{f} = ?")
        vals.append(data[f])
        if f in IDENTITY_FIELDS and (data[f] or None) != (before.get(f) or None):
            identity_changed = True
    vis_changed_to_private = False
    if "visibility" in data:
        vis = parse_visibility(data.get("visibility"))
        sets.append("visibility = ?")
        vals.append(vis)
        vis_changed_to_private = vis == "private" and (before.get("visibility") or "private") != "private"
    if sets:
        sets.append("updated_at = ?")
        vals.extend([db.now(), bean_id])
        conn.execute(f"UPDATE bean SET {', '.join(sets)} WHERE id = ?", vals)
    if "tags" in data:
        set_tags(conn, bean_id, data["tags"] or [])
    if "origin" in data or "producer" in data:
        row = _row(conn.execute("SELECT origin, producer FROM bean WHERE id = ?", (bean_id,)))
        if row:
            places.sync_gazetteer(conn, bean_id, row["origin"], row["producer"])
    if identity_changed or vis_changed_to_private:
        clear_certification(conn, bean_id)


@db.atomic
def delete_bean(conn: sqlite3.Connection, bean_id: int, mode: str | None = None) -> dict:
    """从豆库拿掉一张卡。

    没未撤回消耗：整张物理删（袋子、照片、评分一起走）。
    有未撤回消耗时必须带 mode：
    - keep：只从豆库收起（deleted_at），花掉的钱和杯数留在统计里（钱不回溯）
    - wipe：连流水一起物理删，统计里那几笔钱和杯也没了
    不带 mode 仍 409，避免旧客户端一键抹掉账。
    """
    row = _row(conn.execute("SELECT * FROM bean WHERE id = ?", (bean_id,)))
    if not row:
        raise Conflict("没有这支豆")
    if row.get("deleted_at"):
        raise Conflict("这张卡已经不在豆库里了")

    live = conn.execute(
        """SELECT COUNT(*) FROM consumption_event c
           JOIN bean_lot l ON l.id = c.lot_id
           WHERE l.bean_id = ? AND c.voided_at IS NULL""",
        (bean_id,),
    ).fetchone()[0]
    if live and mode not in ("keep", "wipe"):
        raise Conflict(
            f"这支豆还有 {live} 笔没撤回的记录。删卡时选留下花掉的钱，或连记录一起抹掉"
        )

    if live and mode == "keep":
        now = db.now()
        # 袋子从货架收走，剩下的克不进「在库约多少钱」；已花的钱不动
        conn.execute(
            "UPDATE bean_lot SET closed_at = ? WHERE bean_id = ? AND closed_at IS NULL",
            (now, bean_id),
        )
        conn.execute(
            "UPDATE bean SET deleted_at = ?, updated_at = ? WHERE id = ?",
            (now, now, bean_id),
        )
        conn.execute("DELETE FROM write_lock WHERE resource = ?", (f"bean:{bean_id}",))
        return {"ok": True, "id": bean_id, "name": row["name"], "kept_spend": True, "live": live}

    for path in photos.paths_for_bean(conn, bean_id):
        photos.remove(path)
    # consumption_photo / audit 挂在流水上，流水靠 bean_lot 级联；先手清免得老库外键拦住
    conn.execute(
        """DELETE FROM consumption_photo WHERE cons_id IN (
             SELECT c.id FROM consumption_event c
             JOIN bean_lot l ON l.id = c.lot_id WHERE l.bean_id = ?
           )""",
        (bean_id,),
    )
    conn.execute(
        """DELETE FROM consumption_audit WHERE cons_id IN (
             SELECT c.id FROM consumption_event c
             JOIN bean_lot l ON l.id = c.lot_id WHERE l.bean_id = ?
           )""",
        (bean_id,),
    )
    conn.execute("DELETE FROM write_lock WHERE resource = ?", (f"bean:{bean_id}",))
    conn.execute("DELETE FROM bean WHERE id = ?", (bean_id,))
    return {"ok": True, "id": bean_id, "name": row["name"]}


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


def list_beans(conn: sqlite3.Connection, scope: str = "stock", owner_id: int | None = None) -> list[dict]:
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
        WHERE (? IS NULL OR b.owner_id = ?)
          AND b.deleted_at IS NULL
        ORDER BY b.updated_at DESC
        """,
        (owner_id, owner_id),
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
        out.append(_annotate_bean(b))
    return out


def get_bean(conn: sqlite3.Connection, bean_id: int, owner_id: int | None = None) -> dict | None:
    bean = _row(conn.execute("SELECT * FROM bean WHERE id = ?", (bean_id,)))
    if not bean:
        return None
    if owner_id is not None and bean.get("owner_id") != owner_id:
        return None
    if bean.get("deleted_at"):
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
    bean["places"] = places.list_places(conn, bean_id)
    bean["grind_hint"] = grind_hint_for_bean(conn, bean_id)
    return _annotate_bean(bean)


def plaza_offer(conn: sqlite3.Connection, bean_id: int) -> dict | None:
    """广场给人看的买袋价和袋上克重。最近一袋；不带剩余、实称、批次明细。"""
    row = _row(
        conn.execute(
            """SELECT price, nominal_g
                 FROM bean_lot
                WHERE bean_id = ? AND (price IS NOT NULL OR nominal_g IS NOT NULL)
                ORDER BY created_at DESC, id DESC
                LIMIT 1""",
            (bean_id,),
        )
    )
    if not row:
        return None
    price = row.get("price")
    nominal = row.get("nominal_g")
    offer = {}
    if price is not None:
        offer["price"] = price
    if nominal is not None:
        offer["nominal_g"] = nominal
    return offer or None


def public_card(conn: sqlite3.Connection, bean_id: int, viewer_id: int | None = None) -> dict | None:
    """广场上看的豆卡：产地/照片/杯测/买袋价/袋上克重可以，剩余和流水不给。"""
    bean = _row(
        conn.execute(
            "SELECT * FROM bean WHERE id = ? AND deleted_at IS NULL",
            (bean_id,),
        )
    )
    if not bean or (bean.get("visibility") or "private") != "public":
        return None
    shots = photos.list_bean_photos(conn, bean_id)
    return {
        "id": bean["id"],
        "name": bean["name"],
        "origin": bean.get("origin"),
        "varietal": bean.get("varietal"),
        "producer": bean.get("producer"),
        "altitude": bean.get("altitude"),
        "process": bean.get("process"),
        "roast": bean.get("roast"),
        "water_temp": bean.get("water_temp"),
        "note": bean.get("note"),
        "visibility": "public",
        "certified": bool(bean.get("certified_at")),
        "certified_at": bean.get("certified_at"),
        "places_verified_at": bean.get("places_verified_at"),
        "updated_at": bean.get("updated_at"),
        "tags": bean_tags(conn, bean_id),
        "scores": _public_score(latest_score(conn, bean_id)),
        "places": places.list_places(conn, bean_id),
        "photos": shots,
        "cover": photos.cover(shots),
        "mine": viewer_id is not None and bean.get("owner_id") == viewer_id,
        "kingdom_id": bean.get("kingdom_id"),
        "kingdom": _kingdom_teaser(conn, bean.get("kingdom_id")),
        "offer": plaza_offer(conn, bean_id),
    }


def _kingdom_teaser(conn: sqlite3.Connection, kingdom_id) -> dict | None:
    if not kingdom_id:
        return None
    from . import kingdom

    return kingdom.teaser(conn, kingdom_id)


def split_csv(value) -> list[str]:
    """roast/process/tag 查询：英文或中文逗号都行。列表会摊平。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(split_csv(item))
        return out
    return [p.strip() for p in str(value).replace("，", ",").split(",") if p.strip()]


def plaza_card_matches(
    card: dict,
    *,
    q: str | None = None,
    roast=None,
    process=None,
    tags=None,
    in_kingdom: bool | None = None,
) -> bool:
    """广场筛：烘焙/处理法同一栏多选是或，标签多选是且。"""
    roasts = {r.lower() for r in split_csv(roast)}
    if roasts and (card.get("roast") or "").lower() not in roasts:
        return False
    processes = {p.lower() for p in split_csv(process)}
    if processes and (card.get("process") or "").lower() not in processes:
        return False
    want_tags = split_csv(tags)
    if want_tags:
        have = {t.lower() for t in (card.get("tags") or [])}
        if not all(t.lower() in have for t in want_tags):
            return False
    needle = (q or "").strip().lower()
    if needle:
        hay = [
            card.get("name"),
            card.get("origin"),
            card.get("varietal"),
            card.get("producer"),
            *(card.get("tags") or []),
        ]
        if not any(needle in str(x).lower() for x in hay if x):
            return False
    kid = card.get("kingdom_id")
    has_kingdom = bool(kid)
    if in_kingdom is True and not has_kingdom:
        return False
    if in_kingdom is False and has_kingdom:
        return False
    return True


def list_public_beans(
    conn: sqlite3.Connection,
    *,
    certified_only: bool = False,
    viewer_id: int | None = None,
    q: str | None = None,
    roast=None,
    process=None,
    tags=None,
    in_kingdom: bool | None = None,
) -> list[dict]:
    sql = """SELECT id FROM bean
              WHERE visibility = 'public' AND deleted_at IS NULL"""
    if certified_only:
        sql += " AND certified_at IS NOT NULL"
    sql += " ORDER BY updated_at DESC"
    out = []
    for row in conn.execute(sql):
        card = public_card(conn, row["id"], viewer_id)
        if card and plaza_card_matches(
            card, q=q, roast=roast, process=process, tags=tags, in_kingdom=in_kingdom
        ):
            out.append(card)
    return out


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
    bean = _row(conn.execute("SELECT deleted_at FROM bean WHERE id = ?", (bean_id,)))
    if not bean:
        raise Conflict("没有这支豆")
    if bean.get("deleted_at"):
        raise Conflict("这张卡已经不在豆库里了")
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


@db.atomic
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


def list_people(
    conn: sqlite3.Connection, include_inactive: bool = False, owner_id: int | None = None
) -> list[dict]:
    """带上每人的记录条数，删人前要拿它提示影响面。"""
    where, args = ["1 = 1"], []
    if not include_inactive:
        where.append("p.active = 1")
    if owner_id is not None:
        where.append("p.owner_id = ?")
        args.append(owner_id)
    return _rows(
        conn.execute(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM consumption_event c
                         WHERE c.person_id = p.id AND c.voided_at IS NULL) AS cups
                FROM person p WHERE {' AND '.join(where)}
                ORDER BY p.active DESC, p.name""",
            args,
        )
    )


def ensure_person(conn: sqlite3.Connection, name: str | None, owner_id: int | None = None) -> int | None:
    """输入即创建。名字为空表示不记是谁。同名只在同一账号下算重复。"""
    if not name or not name.strip():
        return None
    name = name.strip()
    if owner_id is None:
        row = conn.execute(
            "SELECT id FROM person WHERE name = ? AND owner_id IS NULL", (name,)
        ).fetchone()
        if row:
            return int(row[0])
        cur = conn.execute(
            "INSERT INTO person (name, owner_id, created_at) VALUES (?, NULL, ?)",
            (name, db.now()),
        )
        return int(cur.lastrowid)
    conn.execute(
        """INSERT INTO person (name, owner_id, created_at) VALUES (?, ?, ?)
           ON CONFLICT(owner_id, name) DO NOTHING""",
        (name, owner_id, db.now()),
    )
    return int(
        conn.execute(
            "SELECT id FROM person WHERE name = ? AND owner_id = ?", (name, owner_id)
        ).fetchone()[0]
    )


def rename_person(conn: sqlite3.Connection, person_id: int, name: str) -> None:
    """改名只改这一行；历史流水通过外键自动跟着变。"""
    name = name.strip()
    if not name:
        raise Conflict("名字不能为空")
    owner = conn.execute("SELECT owner_id FROM person WHERE id = ?", (person_id,)).fetchone()
    exists = conn.execute(
        "SELECT id FROM person WHERE name = ? AND id <> ? AND owner_id IS ?",
        (name, person_id, owner["owner_id"] if owner else None),
    ).fetchone()
    if exists:
        raise Conflict(f"已经有叫「{name}」的人了")
    conn.execute("UPDATE person SET name = ? WHERE id = ?", (name, person_id))


def set_person_active(conn: sqlite3.Connection, person_id: int, active: bool) -> None:
    """停用是轻量选项：选人列表里不再出现，名字和归属都还在。"""
    conn.execute("UPDATE person SET active = ? WHERE id = ?", (1 if active else 0, person_id))


@db.atomic
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


@db.atomic
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

    person_id = data.get("person_id") or ensure_person(conn, data.get("person"), data.get("owner_id"))
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
    out = {
        "id": int(cur.lastrowid),
        "lot_id": lot["id"],
        "amount_g": amount,
        "cost": (amount * lot["unit_cost"]) if lot["unit_cost"] else None,
        "as_cup": as_cup,
        "balance_g": after["balance_g"],
        "near_empty": after["balance_g"] < amount,
    }
    compared = brew.compare(
        data.get("brew_method"), amount, data.get("brew_ratio"), data.get("brew_total_s")
    )
    if compared:
        out["brew_compare"] = compared
    return out


@db.atomic
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


@db.atomic
def void_one(conn: sqlite3.Connection, cons_id: int, reason: str | None = None) -> dict:
    """撤回单行。酒单整巡请走 void_consumption / menu.void_serve。"""
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


@db.atomic
def unvoid_one(conn: sqlite3.Connection, cons_id: int) -> None:
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


@db.atomic
def delete_voided_one(conn: sqlite3.Connection, cons_id: int) -> dict:
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    if not row["voided_at"]:
        raise Conflict("先撤回再删。没撤回的记录还在账上，不能直接抹掉")
    n = photos.purge_consumption_photos(conn, cons_id)
    conn.execute("DELETE FROM consumption_event WHERE id = ?", (cons_id,))
    return {"ok": True, "id": cons_id, "photos_removed": n}


def void_consumption(conn: sqlite3.Connection, cons_id: int, reason: str | None = None) -> dict:
    """撤回一笔：只划掉不删。属于酒单一巡的，整巡一起撤。"""
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    serve_id = row.get("serve_id")
    if serve_id:
        from . import menu as menu_mod

        return menu_mod.void_serve(conn, int(serve_id), reason)
    return void_one(conn, cons_id, reason)


def unvoid_consumption(conn: sqlite3.Connection, cons_id: int) -> None:
    """撤回撤错了，恢复这一笔。属于酒单一巡的，整巡一起恢复。"""
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    serve_id = row.get("serve_id")
    if serve_id:
        from . import menu as menu_mod

        menu_mod.unvoid_serve(conn, int(serve_id))
        return
    unvoid_one(conn, cons_id)


@db.atomic
def delete_voided_consumption(conn: sqlite3.Connection, cons_id: int) -> dict:
    """彻底删掉已经撤回的一笔。库存在撤回时已经加回去，这里不再动账。"""
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    serve_id = row.get("serve_id")
    if serve_id:
        from . import menu as menu_mod

        return menu_mod.delete_voided_serve(conn, int(serve_id))
    return delete_voided_one(conn, cons_id)


def reassign_person(
    conn: sqlite3.Connection, cons_id: int, person: str | None, owner_id: int | None = None
) -> None:
    """人选错了：只改归属，克重不动，库存不变；留痕。"""
    row = _row(conn.execute("SELECT * FROM consumption_event WHERE id = ?", (cons_id,)))
    if not row:
        raise Conflict("没有这条记录")
    old = None
    if row["person_id"]:
        r = conn.execute("SELECT name FROM person WHERE id = ?", (row["person_id"],)).fetchone()
        old = r[0] if r else None
    new_id = ensure_person(conn, person, owner_id)
    serve_id = row.get("serve_id")
    ids = [cons_id]
    if serve_id:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM consumption_event WHERE serve_id = ?", (serve_id,)
            )
        ]
        conn.execute("UPDATE drink_serve SET person_id = ? WHERE id = ?", (new_id, serve_id))
    for cid in ids:
        conn.execute("UPDATE consumption_event SET person_id = ? WHERE id = ?", (new_id, cid))
        conn.execute(
            """INSERT INTO consumption_audit (cons_id, field, old_value, new_value, at)
               VALUES (?, 'person', ?, ?, ?)""",
            (cid, old, (person or "").strip() or None, db.now()),
        )


def list_consumption(
    conn: sqlite3.Connection,
    bean_id: int | None = None,
    bottle_id: int | None = None,
    person_id: int | None = None,
    owner_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """明细含已撤回的行（界面上划掉显示），汇总统计一律排除。"""
    where, args = ["1 = 1"], []
    if owner_id is not None:
        where.append("(b.owner_id = ? OR sp.owner_id = ?)")
        args.extend([owner_id, owner_id])
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
        attach_brew_compare(row)
    return out


def attach_brew_compare(row: dict) -> None:
    if row.get("kind") != "coffee" or row.get("as_cup") == 0:
        return
    compared = brew.compare(
        row.get("brew_method"), row.get("amount_g"), row.get("brew_ratio"), row.get("brew_total_s")
    )
    if compared:
        row["brew_compare"] = compared


def grind_hint_for_bean(conn: sqlite3.Connection, bean_id: int) -> dict | None:
    rows = conn.execute(
        """SELECT c.amount_g, c.brew_method, c.brew_ratio, c.brew_total_s
             FROM consumption_event c
             JOIN bean_lot l ON l.id = c.lot_id
            WHERE l.bean_id = ? AND c.kind = 'coffee' AND c.voided_at IS NULL
              AND c.as_cup = 1 AND c.brew_total_s IS NOT NULL
              AND c.brew_method IS NOT NULL AND c.brew_ratio IS NOT NULL
            ORDER BY c.at DESC, c.id DESC
            LIMIT 20""",
        (bean_id,),
    ).fetchall()
    if not rows:
        return None
    method = rows[0]["brew_method"]
    same = [dict(r) for r in rows if r["brew_method"] == method][:3]
    return brew.grind_hint(same)
