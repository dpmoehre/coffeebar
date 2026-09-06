"""推荐酒单：纯饮 / 鸡尾酒。一巡多行扣瓶，杯数按巡算。"""

from __future__ import annotations

import sqlite3

from . import db, locks, spirits, store

NEAT_DEFAULT_ML = 30.0


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _row(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


def recipe_owner(conn: sqlite3.Connection, recipe_id: int) -> int | None:
    row = conn.execute("SELECT owner_id FROM recipe WHERE id = ?", (recipe_id,)).fetchone()
    return None if not row else row["owner_id"]


def menu_item_owner(conn: sqlite3.Connection, item_id: int) -> int | None:
    row = conn.execute("SELECT owner_id FROM menu_item WHERE id = ?", (item_id,)).fetchone()
    return None if not row else row["owner_id"]


def serve_owner(conn: sqlite3.Connection, serve_id: int) -> int | None:
    row = conn.execute("SELECT owner_id FROM drink_serve WHERE id = ?", (serve_id,)).fetchone()
    return None if not row else row["owner_id"]


def _lines_of(conn: sqlite3.Connection, recipe_id: int) -> list[dict]:
    return _rows(
        conn.execute(
            """SELECT rl.id, rl.spirit_id, rl.amount_ml, rl.sort,
                      b.name AS spirit_name, b.abv, b.kind, b.owner_id AS spirit_owner_id
               FROM recipe_line rl JOIN bottle b ON b.id = rl.spirit_id
               WHERE rl.recipe_id = ? ORDER BY rl.sort, rl.id""",
            (recipe_id,),
        )
    )


def _alts_same_kind(conn: sqlite3.Connection, kind: str, owner_id: int | None) -> list[dict]:
    """同一大类、还在库的酒。倒的时候可换支，不自挑第几瓶。"""
    if not kind:
        return []
    out = []
    for s in spirits.list_spirits(conn, "stock", owner_id):
        if s.get("kind") != kind or s.get("pending"):
            continue
        lots = [l for l in spirits.list_lots(conn, s["id"]) if not l.get("closed_at")]
        out.append(
            {
                "spirit_id": s["id"],
                "spirit_name": s["name"],
                "balance_ml": round(float(s.get("balance_ml") or 0), 1),
                "open_lots": [
                    {"lot_id": l["id"], "seq": l.get("seq"), "balance_ml": l.get("balance_ml")}
                    for l in lots
                ],
            }
        )
    return out


def _attach_stock(conn: sqlite3.Connection, line: dict) -> dict:
    kind = spirits.normalize_kind(line.get("kind"), None, line.get("spirit_name"))
    line["kind"] = kind
    lots = [l for l in spirits.list_lots(conn, line["spirit_id"]) if not l.get("closed_at")]
    line["open_lots"] = [
        {"lot_id": l["id"], "seq": l.get("seq"), "balance_ml": l.get("balance_ml")} for l in lots
    ]
    line["balance_ml"] = round(sum(l["balance_ml"] for l in lots), 1)
    line["enough"] = line["balance_ml"] >= float(line["amount_ml"] or 0)
    line["alts"] = _alts_same_kind(conn, kind, line.get("spirit_owner_id"))
    return line


def get_recipe(conn: sqlite3.Connection, recipe_id: int, owner_id: int | None = None) -> dict | None:
    rec = _row(conn.execute("SELECT * FROM recipe WHERE id = ?", (recipe_id,)))
    if not rec:
        return None
    if owner_id is not None and rec.get("owner_id") != owner_id:
        return None
    rec["lines"] = [_attach_stock(conn, ln) for ln in _lines_of(conn, recipe_id)]
    return rec


def list_recipes(conn: sqlite3.Connection, owner_id: int) -> list[dict]:
    out = []
    for r in conn.execute(
        "SELECT * FROM recipe WHERE owner_id IS ? ORDER BY updated_at DESC, id DESC", (owner_id,)
    ):
        rec = dict(r)
        rec["lines"] = [_attach_stock(conn, ln) for ln in _lines_of(conn, rec["id"])]
        out.append(rec)
    return out


def _replace_lines(conn: sqlite3.Connection, recipe_id: int, lines: list[dict]) -> None:
    if not lines:
        raise store.Conflict("鸡尾酒至少要选一支基酒")
    conn.execute("DELETE FROM recipe_line WHERE recipe_id = ?", (recipe_id,))
    for i, ln in enumerate(lines):
        sid = int(ln["spirit_id"])
        ml = float(ln.get("amount_ml") or 0)
        if ml <= 0:
            raise store.Conflict("配方用量要大于 0")
        if not conn.execute("SELECT id FROM bottle WHERE id = ?", (sid,)).fetchone():
            raise store.Conflict("没有这支基酒")
        conn.execute(
            "INSERT INTO recipe_line (recipe_id, spirit_id, amount_ml, sort) VALUES (?, ?, ?, ?)",
            (recipe_id, sid, ml, int(ln.get("sort") or i)),
        )


def create_recipe(conn: sqlite3.Connection, data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise store.Conflict("鸡尾酒得有个名字")
    ts = db.now()
    cur = conn.execute(
        """INSERT INTO recipe (owner_id, name, steps, note, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data["owner_id"], name, data.get("steps"), data.get("note"), ts, ts),
    )
    rid = int(cur.lastrowid)
    _replace_lines(conn, rid, data.get("lines") or [])
    return get_recipe(conn, rid, data["owner_id"])


def update_recipe(conn: sqlite3.Connection, recipe_id: int, data: dict) -> dict:
    rec = get_recipe(conn, recipe_id)
    if not rec:
        raise store.Conflict("没有这个配方")
    fields, args = [], []
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise store.Conflict("鸡尾酒得有个名字")
        fields.append("name = ?")
        args.append(name)
    if "steps" in data:
        fields.append("steps = ?")
        args.append(data.get("steps"))
    if "note" in data:
        fields.append("note = ?")
        args.append(data.get("note"))
    fields.append("updated_at = ?")
    args.append(db.now())
    args.append(recipe_id)
    conn.execute(f"UPDATE recipe SET {', '.join(fields)} WHERE id = ?", args)
    if "lines" in data:
        _replace_lines(conn, recipe_id, data.get("lines") or [])
    return get_recipe(conn, recipe_id, rec.get("owner_id"))


def delete_recipe(conn: sqlite3.Connection, recipe_id: int) -> None:
    live = conn.execute(
        """SELECT 1 FROM drink_serve s
           JOIN consumption_event c ON c.serve_id = s.id
           WHERE s.recipe_id = ? AND c.voided_at IS NULL LIMIT 1""",
        (recipe_id,),
    ).fetchone()
    if live:
        raise store.Conflict("还有没撤回的出品用过这个配方，先撤回再删")
    conn.execute("DELETE FROM recipe WHERE id = ?", (recipe_id,))


def _item_view(conn: sqlite3.Connection, item: dict) -> dict:
    if item["kind"] == "neat":
        bottle = spirits.get_spirit(conn, item["spirit_id"])
        name = bottle["name"] if bottle else "已不在库"
        line = _attach_stock(
            conn,
            {
                "spirit_id": item["spirit_id"],
                "spirit_name": name,
                "amount_ml": NEAT_DEFAULT_ML,
                "sort": 0,
                "abv": bottle.get("abv") if bottle else None,
                "kind": bottle.get("kind") if bottle else None,
                "spirit_owner_id": bottle.get("owner_id") if bottle else None,
            },
        )
        item["name"] = name
        item["lines"] = [line]
        item["enough"] = line["enough"]
        item["steps"] = None
        item["note"] = bottle.get("note") if bottle else None
    else:
        rec = get_recipe(conn, item["recipe_id"])
        item["name"] = rec["name"] if rec else "已删配方"
        item["lines"] = rec["lines"] if rec else []
        item["enough"] = all(ln.get("enough") for ln in item["lines"]) if item["lines"] else False
        item["steps"] = rec.get("steps") if rec else None
        item["note"] = rec.get("note") if rec else None
    return item


def get_item(conn: sqlite3.Connection, item_id: int, owner_id: int | None = None) -> dict | None:
    item = _row(conn.execute("SELECT * FROM menu_item WHERE id = ?", (item_id,)))
    if not item:
        return None
    if owner_id is not None and item.get("owner_id") != owner_id:
        return None
    item["listed"] = bool(item["listed"])
    return _item_view(conn, item)


def list_menu(conn: sqlite3.Connection, owner_id: int, listed_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM menu_item WHERE owner_id IS ?"
    args: list = [owner_id]
    if listed_only:
        sql += " AND listed = 1"
    sql += " ORDER BY sort, id"
    return [_item_view(conn, dict(r)) for r in conn.execute(sql, args)]


def add_menu_item(conn: sqlite3.Connection, data: dict) -> dict:
    kind = data.get("kind")
    if kind not in ("neat", "cocktail"):
        raise store.Conflict("酒单条目只能是纯饮或鸡尾酒")
    owner_id = data["owner_id"]
    if kind == "neat":
        sid = int(data.get("spirit_id") or 0)
        bottle = spirits.get_spirit(conn, sid, owner_id=owner_id)
        if not bottle:
            raise store.Conflict("没有这支基酒")
        dup = conn.execute(
            "SELECT id FROM menu_item WHERE owner_id IS ? AND kind = 'neat' AND spirit_id = ?",
            (owner_id, sid),
        ).fetchone()
        if dup:
            raise store.Conflict("这支酒已经在酒单上了")
        recipe_id = None
    else:
        rid = int(data.get("recipe_id") or 0)
        rec = get_recipe(conn, rid, owner_id)
        if not rec:
            raise store.Conflict("没有这个配方")
        dup = conn.execute(
            "SELECT id FROM menu_item WHERE owner_id IS ? AND kind = 'cocktail' AND recipe_id = ?",
            (owner_id, rid),
        ).fetchone()
        if dup:
            raise store.Conflict("这款鸡尾酒已经在酒单上了")
        sid = None
        recipe_id = rid
    sort = data.get("sort")
    if sort is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort), -1) + 1 FROM menu_item WHERE owner_id IS ?", (owner_id,)
        ).fetchone()
        sort = int(row[0])
    listed = 0 if data.get("listed") is False else 1
    cur = conn.execute(
        """INSERT INTO menu_item (owner_id, kind, spirit_id, recipe_id, sort, listed, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (owner_id, kind, sid, recipe_id, int(sort), listed, db.now()),
    )
    return get_item(conn, int(cur.lastrowid), owner_id)


def set_listed(conn: sqlite3.Connection, item_id: int, listed: bool) -> dict:
    conn.execute("UPDATE menu_item SET listed = ? WHERE id = ?", (1 if listed else 0, item_id))
    item = get_item(conn, item_id)
    if not item:
        raise store.Conflict("没有这条酒单")
    return item


def reorder_menu(conn: sqlite3.Connection, owner_id: int, ids: list[int]) -> list[dict]:
    have = {r[0] for r in conn.execute("SELECT id FROM menu_item WHERE owner_id IS ?", (owner_id,))}
    if set(ids) != have:
        raise store.Conflict("排序要包含这一页全部酒单条目")
    for i, item_id in enumerate(ids):
        conn.execute("UPDATE menu_item SET sort = ? WHERE id = ?", (i, item_id))
    return list_menu(conn, owner_id)


def delete_menu_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM menu_item WHERE id = ?", (item_id,))


def _chosen_spirit(conn: sqlite3.Connection, spec: dict, raw: dict, owner_id: int | None) -> int:
    """配方写死一支；倒的时候可换成同一大类的另一支（金酒换金酒），不能跨类。"""
    chosen = int(raw["spirit_id"])
    if chosen == int(spec["spirit_id"]):
        return chosen
    alt = spirits.get_spirit(conn, chosen, owner_id)
    if not alt:
        raise store.Conflict("没有这支基酒")
    want = spec.get("kind") or spirits.normalize_kind(None, None, spec.get("spirit_name"))
    if alt["kind"] != want:
        raise store.Conflict(f"「{alt['name']}」不是{want}，换同一类的酒")
    if not alt.get("in_stock"):
        raise store.Conflict(f"「{alt['name']}」没有未关的瓶子")
    return chosen


def _pick_lot(conn: sqlite3.Connection, spirit_id: int, lot_id: int | None) -> dict | dict:
    lots = [l for l in spirits.list_lots(conn, spirit_id) if not l.get("closed_at")]
    if not lots:
        raise store.Conflict("这支酒没有未关的瓶子")
    if lot_id is not None:
        lot = next((l for l in lots if l["id"] == int(lot_id)), None)
        if not lot:
            raise store.Conflict("没有这一瓶，或已经关了")
        return lot
    if len(lots) > 1:
        return {
            "error": "有多瓶未关，请指定 lot_id，我不自己挑",
            "spirit_id": spirit_id,
            "lots": [{"lot_id": l["id"], "seq": l.get("seq"), "balance_ml": l.get("balance_ml")} for l in lots],
        }
    return lots[0]


def _guests(data: dict) -> list[dict]:
    """倒酒对象。people 多选 = 一人一杯；空着仍记 1 巡、没记谁。"""
    raw = data.get("people")
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",") if x.strip()]
    if isinstance(raw, list) and raw:
        guests = []
        for x in raw:
            if x in (None, ""):
                continue
            if isinstance(x, int):
                guests.append({"person_id": x})
            else:
                guests.append({"person": str(x).strip()})
        if guests:
            return guests
    if data.get("person_id"):
        return [{"person_id": data["person_id"]}]
    if data.get("person"):
        return [{"person": data["person"]}]
    return [{}]


def _write_serve(conn: sqlite3.Connection, item: dict, data: dict, person_id, ts: str, resolved: list) -> dict:
    cur = conn.execute(
        """INSERT INTO drink_serve
             (owner_id, kind, menu_item_id, recipe_id, person_id, name, note, at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("owner_id"),
            item["kind"],
            item["id"],
            item.get("recipe_id"),
            person_id,
            item["name"],
            data.get("note"),
            ts,
        ),
    )
    serve_id = int(cur.lastrowid)
    for spec, amount, lot in resolved:
        ev = spirits.record_drink(
            conn,
            {
                "lot_id": lot["id"],
                "amount_ml": amount,
                "person_id": person_id,
                "owner_id": data.get("owner_id"),
                "note": data.get("note"),
                "at": ts,
            },
        )
        conn.execute("UPDATE consumption_event SET serve_id = ? WHERE id = ?", (serve_id, ev["id"]))
    return get_serve(conn, serve_id)


def pour(
    conn: sqlite3.Connection,
    data: dict,
    *,
    session_id: str = "anon",
    source: str = "web",
) -> dict:
    """从酒单倒一巡。多选人就是一人一杯。lines 可改毫升，同类可换支。同一支多瓶未关不自挑。有锁整巡不写。"""
    item = get_item(conn, int(data["menu_item_id"]), data.get("owner_id"))
    if not item:
        raise store.Conflict("没有这条酒单")
    guests = _guests(data)
    cups = len(guests)
    incoming = data.get("lines") or []
    if not incoming:
        incoming = [{"spirit_id": ln["spirit_id"], "amount_ml": ln["amount_ml"]} for ln in item["lines"]]
    if len(incoming) != len(item["lines"]):
        raise store.Conflict("材料和配方对不上")

    needs = []
    resolved = []
    remaining: dict[int, float] = {}
    for spec, raw in zip(item["lines"], incoming):
        chosen_id = _chosen_spirit(conn, spec, raw, data.get("owner_id"))
        chosen = spirits.get_spirit(conn, chosen_id, data.get("owner_id")) or spec
        label = chosen.get("name") or spec["spirit_name"]
        amount = float(raw.get("amount_ml") or 0)
        if amount <= 0:
            raise store.Conflict(f"{label} 的毫升要大于 0")
        picked = _pick_lot(conn, chosen_id, raw.get("lot_id"))
        if isinstance(picked, dict) and picked.get("error"):
            needs.append(picked)
            continue
        need = amount * cups
        left = remaining.get(picked["id"], picked["balance_ml"])
        if need > left:
            who = f"{cups} 人 × {amount:g} ml" if cups > 1 else f"{amount:g} ml"
            raise store.Conflict(
                f"{label} 只剩 {left:.0f} ml，不够 {who}。"
                "换一支同类、改用量，或先盘点"
            )
        remaining[picked["id"]] = left - need
        resolved.append((spec, amount, picked))
    if needs:
        return {"error": "有多瓶未关，请指定 lot_id，我不自己挑", "needs": needs}

    bottles = {lot["bottle_id"] for _, _, lot in resolved}
    for bid in bottles:
        locks.check(conn, f"bottle:{bid}", session_id, source)

    ts = data.get("at") or db.now()
    serves = []
    for guest in guests:
        person_id = guest.get("person_id") or store.ensure_person(
            conn, guest.get("person"), data.get("owner_id")
        )
        serves.append(_write_serve(conn, item, data, person_id, ts, resolved))

    first = serves[0]
    if len(serves) == 1:
        return first
    total_ml = round(sum(s.get("amount_ml") or 0 for s in serves), 1)
    total_cost = round(sum(s.get("cost") or 0 for s in serves), 2)
    return {
        "cups": len(serves),
        "serves": serves,
        "kind": first["kind"],
        "name": first["name"],
        "amount_ml": total_ml,
        "cost": total_cost or None,
        "at": first.get("at"),
    }


def get_serve(conn: sqlite3.Connection, serve_id: int) -> dict | None:
    serve = _row(conn.execute("SELECT * FROM drink_serve WHERE id = ?", (serve_id,)))
    if not serve:
        return None
    lines = _rows(
        conn.execute(
            """SELECT c.id, c.amount_ml, c.unit_cost, c.voided_at, c.bottle_lot_id AS lot_id,
                      bl.bottle_id AS spirit_id, sp.name AS spirit_name, sp.abv
               FROM consumption_event c
               JOIN bottle_lot bl ON bl.id = c.bottle_lot_id
               JOIN bottle sp ON sp.id = bl.bottle_id
               WHERE c.serve_id = ?
               ORDER BY c.id""",
            (serve_id,),
        )
    )
    total_ml = 0.0
    cost = 0.0
    alcohol = 0.0
    voided = True
    for ln in lines:
        ln["cost"] = (ln["amount_ml"] * ln["unit_cost"]) if ln["unit_cost"] else None
        ln["alcohol_g"] = spirits.alcohol_g(ln["amount_ml"], ln.get("abv"))
        ln["voided"] = bool(ln["voided_at"])
        if not ln["voided"]:
            voided = False
            total_ml += ln["amount_ml"] or 0
            cost += ln["cost"] or 0
            alcohol += ln["alcohol_g"] or 0
    if not lines:
        voided = False
    person = None
    if serve.get("person_id"):
        row = conn.execute("SELECT name FROM person WHERE id = ?", (serve["person_id"],)).fetchone()
        person = row[0] if row else None
    return {
        **serve,
        "person": person,
        "lines": lines,
        "amount_ml": round(total_ml, 1),
        "cost": round(cost, 2) if cost else None,
        "alcohol_g": round(alcohol, 2) if alcohol else None,
        "voided": voided and bool(lines),
    }


def void_serve(conn: sqlite3.Connection, serve_id: int, reason: str | None = None) -> dict:
    serve = get_serve(conn, serve_id)
    if not serve:
        raise store.Conflict("没有这一巡")
    if serve["voided"]:
        raise store.Conflict("这一巡已经撤回过了")
    last = None
    for ln in serve["lines"]:
        if not ln["voided"]:
            last = store.void_one(conn, ln["id"], reason)
    return last or {"id": serve["lines"][0]["id"] if serve["lines"] else None, "serve_id": serve_id}


def unvoid_serve(conn: sqlite3.Connection, serve_id: int) -> None:
    serve = get_serve(conn, serve_id)
    if not serve:
        raise store.Conflict("没有这一巡")
    for ln in serve["lines"]:
        if ln["voided"]:
            store.unvoid_one(conn, ln["id"])


def delete_voided_serve(conn: sqlite3.Connection, serve_id: int) -> dict:
    serve = get_serve(conn, serve_id)
    if not serve:
        raise store.Conflict("没有这一巡")
    if not serve["voided"]:
        raise store.Conflict("先撤回再删。没撤回的出品还在账上，不能直接抹掉")
    removed = 0
    for ln in serve["lines"]:
        out = store.delete_voided_one(conn, ln["id"])
        removed += out.get("photos_removed") or 0
    conn.execute("DELETE FROM drink_serve WHERE id = ?", (serve_id,))
    return {"ok": True, "id": serve_id, "photos_removed": removed}


def drink_cups_sql(alias: str = "c") -> str:
    """有巡按巡去重，老酒卡倒一杯（serve_id 空）仍按笔。"""
    return (
        f"(COUNT(DISTINCT CASE WHEN {alias}.kind = 'drink' AND {alias}.voided_at IS NULL "
        f"AND {alias}.serve_id IS NOT NULL THEN {alias}.serve_id END)"
        f" + COALESCE(SUM(CASE WHEN {alias}.kind = 'drink' AND {alias}.voided_at IS NULL "
        f"AND {alias}.serve_id IS NULL THEN 1 ELSE 0 END), 0))"
    )
