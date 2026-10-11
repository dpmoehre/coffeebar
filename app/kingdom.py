"""咖啡王国：公共豆种上的一起杯测、评价、收藏。

私人豆卡（库存、进价）仍只自己看。管理员把公开卡收到王国后，
同一支豆只有一条。王国页上亲手打的分仍是一人一条、可改。
挂过来的广场卡上，每次豆卡杯测都列出来，并带上附近那杯的冲煮。
"""

from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException

from . import auth, brew as brew_mod, db, photos, store

# 杯测和冲煮常常一前一后写下。超过这段就不当成同一杯。
BREW_MATCH_S = 6 * 3600

DIMS = ("dry", "flavor", "aftertaste", "acidity", "sweetness", "body", "balance", "overall")


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _author_label(name: str, mine: bool = False) -> str:
    label = (name or "").strip() or auth.FALLBACK_NAME
    return f"{label}（我）" if mine else label


def _score_num(value):
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "杯测分要写成数字") from exc
    if n < 1 or n > 10:
        raise HTTPException(400, "杯测分是 1 到 10")
    return n


def _photos(conn: sqlite3.Connection, kingdom_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, path, created_at FROM kingdom_photo WHERE kingdom_id = ? ORDER BY created_at, id",
        (kingdom_id,),
    ).fetchall()
    return [
        {**dict(r), "url": f"/{r['path']}", "thumb": photos.thumb_url(r["path"])} for r in rows
    ]


def _avg(rows: list[sqlite3.Row]) -> dict | None:
    if not rows:
        return None
    out = {}
    for key in DIMS:
        vals = [r[key] for r in rows if r[key] is not None]
        out[key] = round(sum(vals) / len(vals), 2) if vals else None
    return out


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_cup(a, b) -> bool:
    """收录时拷进王国的那条，和豆卡上同一杯对得上就不重复列。"""
    if _text(a["comment"]) != _text(b["comment"]):
        return False
    return all(_num(a[k]) == _num(b[k]) for k in DIMS)


def _stages(raw) -> list[dict]:
    if isinstance(raw, list):
        data = raw
    elif not raw:
        return []
    else:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return []
    if not isinstance(data, list):
        return []
    keep = ("name", "add_g", "target_g", "add_ratio", "target_ratio", "elapsed_s", "seconds")
    out = []
    for item in data:
        if isinstance(item, dict):
            out.append({k: item.get(k) for k in keep})
    return out


def _brew_public(row) -> dict | None:
    """冲煮写给王国看的那一层。不带单价、库存、滤纸钱。"""
    method = row["brew_method"]
    stages = _stages(row["brew_stages"])
    note = _text(row["note"])
    dose = row["amount_g"]
    ratio = row["brew_ratio"]
    total_s = row["brew_total_s"]
    if method is None and dose is None and ratio is None and total_s is None and not note and not stages:
        return None
    label = brew_mod.METHODS.get(method, method) if method else None
    return {
        "method": method,
        "method_label": label,
        "dose_g": dose,
        "ratio": ratio,
        "total_s": total_s,
        "note": note,
        "stages": stages,
    }


def _brews_of(conn: sqlite3.Connection, bean_id: int) -> list:
    return conn.execute(
        """SELECT c.at, c.amount_g, c.brew_method, c.brew_ratio, c.brew_total_s,
                  c.brew_stages, c.note
             FROM consumption_event c
             JOIN bean_lot l ON l.id = c.lot_id
            WHERE l.bean_id = ? AND c.kind = 'coffee' AND c.as_cup = 1
              AND c.voided_at IS NULL""",
        (bean_id,),
    ).fetchall()


def _closest_brew(brews, at: str | None) -> dict | None:
    if not at or not brews:
        return None
    try:
        target = db.parse(at)
    except (TypeError, ValueError):
        return None
    best = None
    gap = None
    for row in brews:
        try:
            delta = abs((db.parse(row["at"]) - target).total_seconds())
        except (TypeError, ValueError):
            continue
        if delta <= BREW_MATCH_S and (gap is None or delta < gap):
            best = row
            gap = delta
    return _brew_public(best) if best else None


def _score_public(conn: sqlite3.Connection, row: sqlite3.Row, *, name: str, mine: bool) -> dict:
    d = {k: row[k] for k in DIMS}
    d["id"] = row["id"]
    d["key"] = f"kingdom-{row['id']}"
    d["source"] = "kingdom"
    d["comment"] = row["comment"]
    d["at"] = row["updated_at"] or row["created_at"]
    d["author"] = _author_label(name, mine)
    d["mine"] = mine
    d["photos"] = photos.list_kingdom_score_photos(conn, row["id"])
    d["brew"] = None
    return d


def cupping_log(conn: sqlite3.Connection, kingdom_id: int, viewer_id: int | None) -> list[dict]:
    """广场卡上的每一次豆卡杯测，加上王国页上多出来的那条。

    收录时种进去的王国分如果和豆卡上同一杯一样，只留豆卡那条，避免看两遍。
    """
    cards = conn.execute(
        """SELECT b.id, b.owner_id, a.nickname
             FROM bean b JOIN account a ON a.id = b.owner_id
            WHERE b.kingdom_id = ? AND b.deleted_at IS NULL AND b.visibility = 'public'
            ORDER BY b.id""",
        (kingdom_id,),
    ).fetchall()
    events: list[dict] = []
    for card in cards:
        brews = _brews_of(conn, card["id"])
        name = auth.public_name(card)
        mine = viewer_id == card["owner_id"]
        rows = conn.execute(
            "SELECT * FROM bean_score WHERE bean_id = ? ORDER BY at DESC, id DESC",
            (card["id"],),
        ).fetchall()
        for row in rows:
            item = {k: row[k] for k in DIMS}
            item.update(
                {
                    "id": row["id"],
                    "key": f"card-{row['id']}",
                    "source": "card",
                    "comment": row["comment"],
                    "at": row["at"],
                    "author_id": card["owner_id"],
                    "author": _author_label(name, mine),
                    "mine": mine,
                    "photos": [],
                    "brew": _closest_brew(brews, row["at"]),
                }
            )
            events.append(item)

    authors = {
        r["id"]: auth.public_name(r)
        for r in conn.execute(
            """SELECT a.id, a.nickname FROM account a
               JOIN kingdom_score s ON s.author_id = a.id WHERE s.kingdom_id = ?""",
            (kingdom_id,),
        )
    }
    kingdom_rows = conn.execute(
        "SELECT * FROM kingdom_score WHERE kingdom_id = ? ORDER BY updated_at DESC, id DESC",
        (kingdom_id,),
    ).fetchall()
    for row in kingdom_rows:
        match = next(
            (
                ev
                for ev in events
                if ev.get("author_id") == row["author_id"] and _same_cup(ev, row)
            ),
            None,
        )
        if match is not None:
            shots = photos.list_kingdom_score_photos(conn, row["id"])
            if shots and not match["photos"]:
                match["photos"] = shots
            continue
        pub = _score_public(
            conn,
            row,
            name=authors.get(row["author_id"], ""),
            mine=viewer_id == row["author_id"],
        )
        pub["author_id"] = row["author_id"]
        events.append(pub)

    events.sort(key=lambda s: (s.get("at") or "", int(s["id"])), reverse=True)
    for ev in events:
        ev.pop("author_id", None)
    return events


def _brief(conn: sqlite3.Connection, row: sqlite3.Row, viewer_id: int | None) -> dict:
    kid = row["id"]
    scores = cupping_log(conn, kid, viewer_id)
    favs = conn.execute(
        "SELECT COUNT(*) FROM kingdom_favorite WHERE kingdom_id = ?", (kid,)
    ).fetchone()[0]
    mine_fav = False
    mine_score = None
    if viewer_id:
        mine_fav = bool(
            conn.execute(
                "SELECT 1 FROM kingdom_favorite WHERE kingdom_id = ? AND account_id = ?",
                (kid, viewer_id),
            ).fetchone()
        )
        mine = next((s for s in scores if s["mine"]), None)
        if mine:
            mine_score = mine["overall"]
    shots = _photos(conn, kid)
    plaza_cards = conn.execute(
        """SELECT COUNT(*) FROM bean
            WHERE kingdom_id = ? AND deleted_at IS NULL AND visibility = 'public'""",
        (kid,),
    ).fetchone()[0]
    return {
        "id": kid,
        "name": row["name"],
        "origin": row["origin"],
        "varietal": row["varietal"],
        "producer": row["producer"],
        "altitude": row["altitude"],
        "process": row["process"],
        "roast": row["roast"],
        "note": row["note"],
        "updated_at": row["updated_at"],
        "cover": photos.with_list(shots[-1]) if shots else None,
        "avg": _avg(scores),
        "cups": len(scores),
        "favorites": favs,
        "favorited": mine_fav,
        "mine_overall": mine_score,
        "plaza_cards": plaza_cards,
    }


def teaser(conn: sqlite3.Connection, kingdom_id: int | None) -> dict | None:
    """广场卡上挂的那一小条：王国名字、均分、杯测次数。"""
    if not kingdom_id:
        return None
    row = conn.execute("SELECT * FROM kingdom_bean WHERE id = ?", (kingdom_id,)).fetchone()
    if not row:
        return None
    brief = _brief(conn, row, None)
    return {
        "id": brief["id"],
        "name": brief["name"],
        "avg": brief["avg"],
        "cups": brief["cups"],
        "favorites": brief["favorites"],
        "plaza_cards": brief["plaza_cards"],
    }


def list_kingdom(conn: sqlite3.Connection, viewer_id: int | None, *, saved: bool = False) -> list[dict]:
    rows = conn.execute("SELECT * FROM kingdom_bean ORDER BY updated_at DESC, id DESC").fetchall()
    out = [_brief(conn, r, viewer_id) for r in rows]
    if saved:
        out = [x for x in out if x["favorited"]]
    out.sort(key=lambda x: (-x["cups"], -x["favorites"], x["name"]))
    return out


def get_kingdom(conn: sqlite3.Connection, kingdom_id: int, viewer_id: int | None) -> dict | None:
    row = conn.execute("SELECT * FROM kingdom_bean WHERE id = ?", (kingdom_id,)).fetchone()
    if not row:
        return None
    out = _brief(conn, row, viewer_id)
    out["photos"] = _photos(conn, kingdom_id)
    out["scores"] = cupping_log(conn, kingdom_id, viewer_id)
    out["mine"] = next((s for s in out["scores"] if s["mine"]), None)
    linked = conn.execute(
        """SELECT id, name, visibility FROM bean
            WHERE kingdom_id = ? AND deleted_at IS NULL AND visibility = 'public'
            ORDER BY id""",
        (kingdom_id,),
    ).fetchall()
    out["cards"] = [dict(r) for r in linked]
    return out


def queue(conn: sqlite3.Connection) -> list[dict]:
    """公开了、还没进王国的豆卡。"""
    rows = conn.execute(
        """SELECT b.id, b.name, b.origin, b.roast, b.visibility, b.certified_at,
                  a.email AS owner_email, a.nickname AS owner_nickname
             FROM bean b JOIN account a ON a.id = b.owner_id
            WHERE b.visibility = 'public' AND b.deleted_at IS NULL AND b.kingdom_id IS NULL
            ORDER BY b.updated_at DESC"""
    ).fetchall()
    return [{**dict(r), "certified": bool(r["certified_at"])} for r in rows]


def collect(conn: sqlite3.Connection, admin: dict, bean_id: int, data: dict | None = None) -> dict:
    data = data or {}
    bean = conn.execute(
        "SELECT * FROM bean WHERE id = ? AND deleted_at IS NULL", (bean_id,)
    ).fetchone()
    if not bean:
        raise HTTPException(404, "没有这支豆")
    if (bean["visibility"] or "private") != "public":
        raise HTTPException(400, "先让主人公开这张卡")
    if bean["kingdom_id"]:
        raise HTTPException(409, "这张卡已经在王国里")

    kingdom_id = data.get("kingdom_id")
    if kingdom_id:
        row = conn.execute("SELECT id FROM kingdom_bean WHERE id = ?", (int(kingdom_id),)).fetchone()
        if not row:
            raise HTTPException(404, "王国里没有这一支")
        kingdom_id = int(kingdom_id)
    else:
        name = _clean(data.get("name")) or bean["name"]
        now = db.now()
        cur = conn.execute(
            """INSERT INTO kingdom_bean
               (name, origin, varietal, producer, altitude, process, roast, note,
                source_bean_id, collected_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                _clean(data["origin"]) if "origin" in data else bean["origin"],
                _clean(data["varietal"]) if "varietal" in data else bean["varietal"],
                _clean(data["producer"]) if "producer" in data else bean["producer"],
                _clean(data["altitude"]) if "altitude" in data else bean["altitude"],
                _clean(data["process"]) if "process" in data else bean["process"],
                _clean(data["roast"]) if "roast" in data else bean["roast"],
                _clean(data["note"]) if "note" in data else bean["note"],
                bean_id,
                admin["id"],
                now,
                now,
            ),
        )
        kingdom_id = int(cur.lastrowid)
        shots = photos.list_bean_photos(conn, bean_id)
        cover = photos.cover_of_bean(conn, bean_id, shots)
        if cover:
            photos.copy_to_kingdom(conn, kingdom_id, cover["path"])

    conn.execute(
        "UPDATE bean SET kingdom_id = ?, updated_at = ? WHERE id = ?",
        (kingdom_id, db.now(), bean_id),
    )
    conn.execute("UPDATE kingdom_bean SET updated_at = ? WHERE id = ?", (db.now(), kingdom_id))

    latest = store.latest_score(conn, bean_id)
    if latest and bean["owner_id"]:
        exists = conn.execute(
            "SELECT id FROM kingdom_score WHERE kingdom_id = ? AND author_id = ?",
            (kingdom_id, bean["owner_id"]),
        ).fetchone()
        if not exists:
            now = db.now()
            conn.execute(
                f"""INSERT INTO kingdom_score
                    (kingdom_id, author_id, {", ".join(DIMS)}, comment, created_at, updated_at)
                    VALUES (?, ?, {", ".join("?" * len(DIMS))}, ?, ?, ?)""",
                (
                    kingdom_id,
                    bean["owner_id"],
                    *[latest.get(k) for k in DIMS],
                    latest.get("comment"),
                    now,
                    now,
                ),
            )
    return get_kingdom(conn, kingdom_id, admin["id"])


def update_kingdom(conn: sqlite3.Connection, kingdom_id: int, data: dict) -> dict:
    row = conn.execute("SELECT * FROM kingdom_bean WHERE id = ?", (kingdom_id,)).fetchone()
    if not row:
        raise HTTPException(404, "王国里没有这一支")
    fields = {
        "name": _clean(data["name"]) if "name" in data else row["name"],
        "origin": _clean(data["origin"]) if "origin" in data else row["origin"],
        "varietal": _clean(data["varietal"]) if "varietal" in data else row["varietal"],
        "producer": _clean(data["producer"]) if "producer" in data else row["producer"],
        "altitude": _clean(data["altitude"]) if "altitude" in data else row["altitude"],
        "process": _clean(data["process"]) if "process" in data else row["process"],
        "roast": _clean(data["roast"]) if "roast" in data else row["roast"],
        "note": _clean(data["note"]) if "note" in data else row["note"],
    }
    if not fields["name"]:
        raise HTTPException(400, "先写豆名")
    conn.execute(
        """UPDATE kingdom_bean
              SET name=?, origin=?, varietal=?, producer=?, altitude=?, process=?, roast=?, note=?, updated_at=?
            WHERE id=?""",
        (*fields.values(), db.now(), kingdom_id),
    )
    return get_kingdom(conn, kingdom_id, None)


def upsert_score(conn: sqlite3.Connection, kingdom_id: int, author_id: int, data: dict) -> dict:
    if not conn.execute("SELECT id FROM kingdom_bean WHERE id = ?", (kingdom_id,)).fetchone():
        raise HTTPException(404, "王国里没有这一支")
    nums = {k: _score_num(data.get(k)) for k in DIMS}
    comment = _clean(data.get("comment"))
    if not any(v is not None for v in nums.values()) and not comment:
        raise HTTPException(400, "至少打一个分，或写一句评价")
    now = db.now()
    existing = conn.execute(
        "SELECT id FROM kingdom_score WHERE kingdom_id = ? AND author_id = ?",
        (kingdom_id, author_id),
    ).fetchone()
    if existing:
        conn.execute(
            f"""UPDATE kingdom_score SET {", ".join(f"{k}=?" for k in DIMS)}, comment=?, updated_at=?
                 WHERE id=?""",
            (*[nums[k] for k in DIMS], comment, now, existing["id"]),
        )
    else:
        conn.execute(
            f"""INSERT INTO kingdom_score
                (kingdom_id, author_id, {", ".join(DIMS)}, comment, created_at, updated_at)
                VALUES (?, ?, {", ".join("?" * len(DIMS))}, ?, ?, ?)""",
            (kingdom_id, author_id, *[nums[k] for k in DIMS], comment, now, now),
        )
    conn.execute("UPDATE kingdom_bean SET updated_at = ? WHERE id = ?", (now, kingdom_id))
    return get_kingdom(conn, kingdom_id, author_id)


def delete_score(conn: sqlite3.Connection, kingdom_id: int, author_id: int) -> dict:
    row = conn.execute(
        "SELECT id FROM kingdom_score WHERE kingdom_id = ? AND author_id = ?",
        (kingdom_id, author_id),
    ).fetchone()
    if row:
        photos.purge_kingdom_score_photos(conn, row["id"])
        conn.execute("DELETE FROM kingdom_score WHERE id = ?", (row["id"],))
    return get_kingdom(conn, kingdom_id, author_id)


def _mine_score_id(conn: sqlite3.Connection, kingdom_id: int, author_id: int) -> int:
    row = conn.execute(
        "SELECT id FROM kingdom_score WHERE kingdom_id = ? AND author_id = ?",
        (kingdom_id, author_id),
    ).fetchone()
    if not row:
        raise HTTPException(409, "先记下杯测，再挂图")
    return row["id"]


def add_score_photo(
    conn: sqlite3.Connection, kingdom_id: int, author_id: int, raw: bytes, filename: str
) -> dict:
    if not conn.execute("SELECT id FROM kingdom_bean WHERE id = ?", (kingdom_id,)).fetchone():
        raise HTTPException(404, "王国里没有这一支")
    score_id = _mine_score_id(conn, kingdom_id, author_id)
    photos.attach_kingdom_score_photo(conn, score_id, raw, filename)
    return get_kingdom(conn, kingdom_id, author_id)


def delete_score_photo(
    conn: sqlite3.Connection, photo_id: int, author_id: int
) -> dict:
    row = conn.execute(
        """SELECT p.id, s.author_id, s.kingdom_id
             FROM kingdom_score_photo p
             JOIN kingdom_score s ON s.id = p.score_id
            WHERE p.id = ?""",
        (photo_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "没有这张图")
    if row["author_id"] != author_id:
        raise HTTPException(403, "只能删自己杯测上的图")
    photos.delete_kingdom_score_photo(conn, photo_id)
    return get_kingdom(conn, row["kingdom_id"], author_id)


def toggle_favorite(conn: sqlite3.Connection, kingdom_id: int, account_id: int) -> dict:
    if not conn.execute("SELECT id FROM kingdom_bean WHERE id = ?", (kingdom_id,)).fetchone():
        raise HTTPException(404, "王国里没有这一支")
    hit = conn.execute(
        "SELECT 1 FROM kingdom_favorite WHERE kingdom_id = ? AND account_id = ?",
        (kingdom_id, account_id),
    ).fetchone()
    if hit:
        conn.execute(
            "DELETE FROM kingdom_favorite WHERE kingdom_id = ? AND account_id = ?",
            (kingdom_id, account_id),
        )
    else:
        conn.execute(
            "INSERT INTO kingdom_favorite (kingdom_id, account_id, created_at) VALUES (?, ?, ?)",
            (kingdom_id, account_id, db.now()),
        )
    return get_kingdom(conn, kingdom_id, account_id)
