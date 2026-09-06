"""私人咖啡器具 + 管理员收录的公共目录。

器具挂在账号台面上，不是「谁喝的」标签。用户自己登记立刻就能影响冲煮建议；
管理员把大家上传的收到目录里，再挂到现有冲煮方式上，别人也能从目录领走。
"""

from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from . import brew, db, photos

KINDS = {
    "dripper": "滤杯",
    "kettle": "手冲壶",
    "grinder": "磨豆机",
    "scale": "称",
    "server": "分享壶",
    "filter": "滤纸",
    "other": "其他",
}

# 现在这几套手冲都用一张纸。没开包就不扣、不加钱。
PAPER_METHODS = set(brew.METHODS)
RESTOCK_SHEETS = 20

FAMILIES = {
    "dripper": {"cone": "锥形", "flat": "平底", "immersion": "浸泡", "other": "其他"},
    "kettle": {"gooseneck": "细嘴", "other": "其他"},
}


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _check_kind(kind: str) -> str:
    kind = (kind or "dripper").strip()
    if kind not in KINDS:
        raise HTTPException(400, "器具类型不对")
    return kind


def _check_family(kind: str, family: str | None) -> str | None:
    family = _clean(family)
    if not family:
        return None
    allowed = FAMILIES.get(kind)
    if not allowed or family not in allowed:
        raise HTTPException(400, "这种器具没有这个形状")
    return family


def _parse_visibility(value) -> str:
    vis = (value or "private").strip()
    if vis not in ("private", "public"):
        raise HTTPException(400, "公开状态只能是 private 或 public")
    return vis


def _check_method(method: str | None) -> str | None:
    method = _clean(method)
    if not method:
        return None
    if method not in brew.METHODS:
        raise HTTPException(400, "没有这种冲煮方式")
    return method


def _photos_of(conn: sqlite3.Connection, table: str, fk: str, pk: int) -> list[dict]:
    rows = conn.execute(
        f"SELECT id, path, created_at FROM {table} WHERE {fk} = ? ORDER BY created_at, id",
        (pk,),
    ).fetchall()
    return [
        {**dict(r), "url": f"/{r['path']}", "thumb": photos.thumb_url(r["path"])} for r in rows
    ]


def _catalog_brief(conn: sqlite3.Connection, catalog_id: int | None) -> dict | None:
    if not catalog_id:
        return None
    row = conn.execute("SELECT * FROM gear_catalog WHERE id = ?", (catalog_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "family": row["family"],
        "brew_method": row["brew_method"],
        "note": row["note"],
    }


def _public_gear(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    out = dict(row)
    out["kind_label"] = KINDS.get(out["kind"], out["kind"])
    fam = FAMILIES.get(out["kind"], {})
    out["family_label"] = fam.get(out["family"]) if out.get("family") else None
    out["collected"] = bool(out.get("catalog_id"))
    out["photos"] = _photos_of(conn, "user_gear_photo", "gear_id", out["id"])
    out["cover"] = photos.with_list(out["photos"][-1]) if out["photos"] else None
    out["catalog"] = _catalog_brief(conn, out.get("catalog_id"))
    out["visibility"] = out.get("visibility") or "private"
    if out["kind"] == "filter":
        out["packs"] = list_packs(conn, out["id"])
        out["sheets_left"] = sum(p["remaining"] for p in out["packs"] if not p.get("closed_at"))
        out["open_pack"] = next((p for p in out["packs"] if p.get("open")), None)
        out["counting"] = any(True for _ in out["packs"])
    else:
        out["packs"] = []
        out["sheets_left"] = None
        out["open_pack"] = None
        out["counting"] = False
    return out


def _public_catalog(conn: sqlite3.Connection, row: sqlite3.Row, *, owners: bool = False) -> dict:
    out = dict(row)
    out["kind_label"] = KINDS.get(out["kind"], out["kind"])
    fam = FAMILIES.get(out["kind"], {})
    out["family_label"] = fam.get(out["family"]) if out.get("family") else None
    out["photos"] = _photos_of(conn, "gear_catalog_photo", "catalog_id", out["id"])
    out["cover"] = photos.with_list(out["photos"][-1]) if out["photos"] else None
    if owners:
        out["owners"] = conn.execute(
            "SELECT COUNT(*) FROM user_gear WHERE catalog_id = ?", (out["id"],)
        ).fetchone()[0]
    return out


def meta() -> dict:
    return {
        "kinds": [{"key": k, "label": v} for k, v in KINDS.items()],
        "families": {
            kind: [{"key": k, "label": v} for k, v in items.items()]
            for kind, items in FAMILIES.items()
        },
        "methods": [{"key": k, "label": v} for k, v in brew.METHODS.items()],
    }


def list_gear(conn: sqlite3.Connection, owner_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM user_gear WHERE owner_id = ? ORDER BY kind, id",
        (owner_id,),
    ).fetchall()
    return [_public_gear(conn, r) for r in rows]


def get_gear(conn: sqlite3.Connection, gear_id: int, owner_id: int | None = None) -> dict | None:
    row = conn.execute("SELECT * FROM user_gear WHERE id = ?", (gear_id,)).fetchone()
    if not row:
        return None
    if owner_id is not None and row["owner_id"] != owner_id:
        return None
    return _public_gear(conn, row)


def create_gear(conn: sqlite3.Connection, owner_id: int, data: dict) -> dict:
    name = _clean(data.get("name"))
    if not name:
        raise HTTPException(400, "先写器具名字")
    kind = _check_kind(data.get("kind") or "dripper")
    family = _check_family(kind, data.get("family"))
    method = _check_method(data.get("brew_method"))
    catalog_id = data.get("catalog_id")
    if catalog_id:
        cat = conn.execute("SELECT id FROM gear_catalog WHERE id = ?", (int(catalog_id),)).fetchone()
        if not cat:
            raise HTTPException(404, "目录里没有这一件")
        already = conn.execute(
            "SELECT id FROM user_gear WHERE owner_id = ? AND catalog_id = ?",
            (owner_id, int(catalog_id)),
        ).fetchone()
        if already:
            raise HTTPException(409, "这件已经在你台面上")
    vis = _parse_visibility(data["visibility"]) if "visibility" in data else "private"
    source = data.get("source_gear_id")
    now = db.now()
    cur = conn.execute(
        """INSERT INTO user_gear
           (owner_id, catalog_id, name, kind, family, brand, model, brew_method, note,
            visibility, source_gear_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            owner_id,
            int(catalog_id) if catalog_id else None,
            name,
            kind,
            family,
            _clean(data.get("brand")),
            _clean(data.get("model")),
            method,
            _clean(data.get("note")),
            vis,
            int(source) if source else None,
            now,
            now,
        ),
    )
    return get_gear(conn, int(cur.lastrowid), owner_id)


def update_gear(conn: sqlite3.Connection, gear_id: int, owner_id: int, data: dict) -> dict:
    row = get_gear(conn, gear_id, owner_id)
    if not row:
        raise HTTPException(404, "没有这件器具")
    name = _clean(data["name"]) if "name" in data else row["name"]
    if not name:
        raise HTTPException(400, "先写器具名字")
    kind = _check_kind(data["kind"]) if "kind" in data else row["kind"]
    family = _check_family(kind, data["family"]) if "family" in data else _check_family(kind, row.get("family"))
    method = _check_method(data["brew_method"]) if "brew_method" in data else row.get("brew_method")
    brand = _clean(data["brand"]) if "brand" in data else row.get("brand")
    model = _clean(data["model"]) if "model" in data else row.get("model")
    note = _clean(data["note"]) if "note" in data else row.get("note")
    vis = _parse_visibility(data["visibility"]) if "visibility" in data else (row.get("visibility") or "private")
    conn.execute(
        """UPDATE user_gear
              SET name=?, kind=?, family=?, brand=?, model=?, brew_method=?, note=?, visibility=?, updated_at=?
            WHERE id=? AND owner_id=?""",
        (name, kind, family, brand, model, method, note, vis, db.now(), gear_id, owner_id),
    )
    return get_gear(conn, gear_id, owner_id)


def delete_gear(conn: sqlite3.Connection, gear_id: int, owner_id: int) -> None:
    row = get_gear(conn, gear_id, owner_id)
    if not row:
        raise HTTPException(404, "没有这件器具")
    photos.purge_gear_photos(conn, gear_id)
    conn.execute("UPDATE gear_catalog SET source_gear_id = NULL WHERE source_gear_id = ?", (gear_id,))
    conn.execute("DELETE FROM user_gear WHERE id = ? AND owner_id = ?", (gear_id, owner_id))


def add_from_catalog(conn: sqlite3.Connection, owner_id: int, catalog_id: int) -> dict:
    cat = get_catalog(conn, catalog_id)
    if not cat:
        raise HTTPException(404, "目录里没有这一件")
    return create_gear(
        conn,
        owner_id,
        {
            "name": cat["name"],
            "kind": cat["kind"],
            "family": cat["family"],
            "brand": cat["brand"],
            "model": cat["model"],
            "brew_method": cat["brew_method"],
            "catalog_id": cat["id"],
        },
    )


def list_catalog(conn: sqlite3.Connection, *, owners: bool = False) -> list[dict]:
    rows = conn.execute("SELECT * FROM gear_catalog ORDER BY kind, name, id").fetchall()
    return [_public_catalog(conn, r, owners=owners) for r in rows]


def get_catalog(conn: sqlite3.Connection, catalog_id: int, *, owners: bool = False) -> dict | None:
    row = conn.execute("SELECT * FROM gear_catalog WHERE id = ?", (catalog_id,)).fetchone()
    if not row:
        return None
    return _public_catalog(conn, row, owners=owners)


def queue(conn: sqlite3.Connection) -> list[dict]:
    """还没被收录的私人器具，管理员收集用。"""
    rows = conn.execute(
        """SELECT g.*, a.email AS owner_email
             FROM user_gear g
             JOIN account a ON a.id = g.owner_id
            WHERE g.catalog_id IS NULL
            ORDER BY g.created_at DESC, g.id DESC"""
    ).fetchall()
    out = []
    for r in rows:
        item = _public_gear(conn, r)
        item["owner_email"] = r["owner_email"]
        item["owner_id"] = r["owner_id"]
        out.append(item)
    return out


def _catalog_fields(data: dict, fallback: dict) -> dict:
    kind = _check_kind(data.get("kind") or fallback.get("kind") or "dripper")
    name = _clean(data.get("name")) or fallback.get("name")
    if not name:
        raise HTTPException(400, "先写器具名字")
    return {
        "name": name,
        "kind": kind,
        "family": _check_family(kind, data["family"] if "family" in data else fallback.get("family")),
        "brand": _clean(data["brand"]) if "brand" in data else _clean(fallback.get("brand")),
        "model": _clean(data["model"]) if "model" in data else _clean(fallback.get("model")),
        "brew_method": _check_method(
            data["brew_method"] if "brew_method" in data else fallback.get("brew_method")
        ),
        "note": _clean(data["note"]) if "note" in data else _clean(fallback.get("note")),
    }


def collect(
    conn: sqlite3.Connection,
    admin: dict,
    gear_id: int,
    data: dict | None = None,
) -> dict:
    """把一件私人器具收到目录：新建一条，或挂到已有目录。"""
    data = data or {}
    row = conn.execute("SELECT * FROM user_gear WHERE id = ?", (gear_id,)).fetchone()
    if not row:
        raise HTTPException(404, "没有这件器具")
    gear = _public_gear(conn, row)
    catalog_id = data.get("catalog_id")
    if catalog_id:
        cat = get_catalog(conn, int(catalog_id), owners=True)
        if not cat:
            raise HTTPException(404, "目录里没有这一件")
    else:
        fields = _catalog_fields(data, gear)
        now = db.now()
        cur = conn.execute(
            """INSERT INTO gear_catalog
               (name, kind, family, brand, model, brew_method, note, source_gear_id, collected_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fields["name"],
                fields["kind"],
                fields["family"],
                fields["brand"],
                fields["model"],
                fields["brew_method"],
                fields["note"],
                gear_id,
                admin["id"],
                now,
                now,
            ),
        )
        catalog_id = int(cur.lastrowid)
        if gear["photos"]:
            photos.copy_to_catalog(conn, catalog_id, gear["photos"][0]["path"])
        cat = get_catalog(conn, catalog_id, owners=True)

    conn.execute(
        "UPDATE user_gear SET catalog_id = ?, brew_method = COALESCE(brew_method, ?), updated_at = ? WHERE id = ?",
        (int(catalog_id), cat.get("brew_method"), db.now(), gear_id),
    )
    return {
        "gear": get_gear(conn, gear_id),
        "catalog": get_catalog(conn, int(catalog_id), owners=True),
    }


def create_catalog(conn: sqlite3.Connection, admin: dict, data: dict) -> dict:
    fields = _catalog_fields(data, {})
    now = db.now()
    cur = conn.execute(
        """INSERT INTO gear_catalog
           (name, kind, family, brand, model, brew_method, note, collected_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fields["name"],
            fields["kind"],
            fields["family"],
            fields["brand"],
            fields["model"],
            fields["brew_method"],
            fields["note"],
            admin["id"],
            now,
            now,
        ),
    )
    return get_catalog(conn, int(cur.lastrowid), owners=True)


def update_catalog(conn: sqlite3.Connection, catalog_id: int, data: dict) -> dict:
    row = get_catalog(conn, catalog_id)
    if not row:
        raise HTTPException(404, "目录里没有这一件")
    fields = _catalog_fields(data, row)
    conn.execute(
        """UPDATE gear_catalog
              SET name=?, kind=?, family=?, brand=?, model=?, brew_method=?, note=?, updated_at=?
            WHERE id=?""",
        (
            fields["name"],
            fields["kind"],
            fields["family"],
            fields["brand"],
            fields["model"],
            fields["brew_method"],
            fields["note"],
            db.now(),
            catalog_id,
        ),
    )
    return get_catalog(conn, catalog_id, owners=True)


def delete_catalog(conn: sqlite3.Connection, catalog_id: int) -> None:
    row = get_catalog(conn, catalog_id)
    if not row:
        raise HTTPException(404, "目录里没有这一件")
    from . import kingdom_gear

    kingdom_gear.purge_catalog_reviews(conn, catalog_id)
    for p in row["photos"]:
        photos.remove(p["path"])
    conn.execute("DELETE FROM gear_catalog WHERE id = ?", (catalog_id,))


def _cloned_gear_id(conn: sqlite3.Connection, source_id: int, viewer_id: int | None) -> int | None:
    if not viewer_id:
        return None
    row = conn.execute(
        "SELECT id FROM user_gear WHERE source_gear_id = ? AND owner_id = ?",
        (source_id, viewer_id),
    ).fetchone()
    return int(row["id"]) if row else None


def plaza_card(conn: sqlite3.Connection, row: sqlite3.Row, viewer_id: int | None) -> dict:
    out = _public_gear(conn, row)
    out.pop("owner_id", None)
    out.pop("packs", None)
    out.pop("open_pack", None)
    out.pop("sheets_left", None)
    out.pop("counting", None)
    out["mine"] = viewer_id is not None and row["owner_id"] == viewer_id
    cloned = _cloned_gear_id(conn, row["id"], viewer_id)
    out["taken"] = bool(cloned)
    out["cloned_id"] = cloned
    from . import kingdom_gear

    out["kingdom"] = kingdom_gear.teaser(conn, out.get("catalog_id"), viewer_id)
    return out


def list_public_gear(conn: sqlite3.Connection, viewer_id: int | None) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM user_gear
            WHERE visibility = 'public'
            ORDER BY updated_at DESC, id DESC"""
    ).fetchall()
    return [plaza_card(conn, r, viewer_id) for r in rows]


def get_public_gear(conn: sqlite3.Connection, gear_id: int, viewer_id: int | None) -> dict | None:
    row = conn.execute("SELECT * FROM user_gear WHERE id = ?", (gear_id,)).fetchone()
    if not row or (row["visibility"] or "private") != "public":
        return None
    return plaza_card(conn, row, viewer_id)


def take_public_gear(conn: sqlite3.Connection, gear_id: int, owner_id: int) -> dict:
    """把别人公开的器具拷到自己台面。图是拷贝。已经领过就还给已有的那件。"""
    row = conn.execute("SELECT * FROM user_gear WHERE id = ?", (gear_id,)).fetchone()
    if not row or (row["visibility"] or "private") != "public":
        raise HTTPException(404, "没有这件公开器具")
    if row["owner_id"] == owner_id:
        raise HTTPException(400, "这是你自己的，不用领")
    already = _cloned_gear_id(conn, gear_id, owner_id)
    if already:
        return get_gear(conn, already, owner_id)
    copied = create_gear(
        conn,
        owner_id,
        {
            "name": row["name"],
            "kind": row["kind"],
            "family": row["family"],
            "brand": row["brand"],
            "model": row["model"],
            "brew_method": row["brew_method"],
            "note": row["note"],
            "source_gear_id": gear_id,
        },
    )
    for shot in _photos_of(conn, "user_gear_photo", "gear_id", gear_id):
        photos.copy_to_user_gear(conn, copied["id"], shot["path"])
    return get_gear(conn, copied["id"], owner_id)


def annotate_methods(conn: sqlite3.Connection, owner_id: int | None) -> list[dict]:
    """给冲煮方式标「你有 / 缺滤杯 / 建议」，并带上目录里的冲煮备注。"""
    owned = list_gear(conn, owner_id) if owner_id else []
    drippers = [g for g in owned if g["kind"] == "dripper"]
    kettles = [g for g in owned if g["kind"] == "kettle"]
    has_gooseneck = any((g.get("family") or "") == "gooseneck" for g in kettles)

    out = []
    for item in brew.methods_payload():
        key = item["key"]
        family = item["family"]
        matched = []
        tips = []
        for g in drippers:
            method = g.get("brew_method") or (g.get("catalog") or {}).get("brew_method")
            fam = g.get("family") or (g.get("catalog") or {}).get("family")
            hit = method == key or (not method and fam == family)
            if not hit:
                continue
            matched.append(g["name"])
            note = (g.get("catalog") or {}).get("note") or g.get("note")
            if note and note not in tips:
                tips.append(note)
        have = None
        if drippers:
            have = bool(matched)
        kettle_tip = None
        if item.get("kettle") == "gooseneck" and kettles and not has_gooseneck:
            kettle_tip = "细嘴壶会更好倒"
        elif item.get("kettle") == "gooseneck" and has_gooseneck:
            kettle_tip = "你有细嘴壶"
        out.append(
            {
                **item,
                "owned": have,
                "gear_names": matched,
                "tips": tips,
                "kettle_tip": kettle_tip,
                "suggested": False,
            }
        )

    if drippers:
        first = next((m for m in out if m["owned"]), None)
        if first:
            first["suggested"] = True
    return out


def list_packs(conn: sqlite3.Connection, gear_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM filter_pack WHERE gear_id = ? ORDER BY id",
        (gear_id,),
    ).fetchall()
    return [_pack_public(r) for r in rows]


def _pack_public(row: sqlite3.Row | dict) -> dict:
    out = dict(row)
    sheets = int(out.get("sheets") or 0)
    price = out.get("price")
    out["unit_cost"] = (float(price) / sheets) if price and sheets else None
    out["open"] = not out.get("closed_at") and int(out.get("remaining") or 0) > 0
    return out


def open_pack(conn: sqlite3.Connection, gear_id: int, owner_id: int, data: dict) -> dict:
    """新开一包才开始计张。不估旧包剩余。"""
    row = get_gear(conn, gear_id, owner_id)
    if not row:
        raise HTTPException(404, "没有这件器具")
    try:
        sheets = int(data.get("sheets") or 0)
    except (TypeError, ValueError):
        sheets = 0
    if sheets <= 0:
        raise HTTPException(400, "先写这一包多少张")
    price = data.get("price")
    if price in ("", None):
        price = None
    else:
        try:
            price = float(price)
        except (TypeError, ValueError):
            raise HTTPException(400, "价钱写数字") from None
        if price < 0:
            raise HTTPException(400, "价钱不能是负的")
    if row["kind"] not in ("filter", "other"):
        raise HTTPException(400, "只有滤纸才能开包")
    if row["kind"] != "filter":
        conn.execute(
            "UPDATE user_gear SET kind = 'filter', updated_at = ? WHERE id = ? AND owner_id = ?",
            (db.now(), gear_id, owner_id),
        )
    now = db.now()
    conn.execute(
        """INSERT INTO filter_pack (gear_id, sheets, price, remaining, opened_on, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (gear_id, sheets, price, sheets, now[:10], now),
    )
    return get_gear(conn, gear_id, owner_id)


def _open_packs(conn: sqlite3.Connection, owner_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT p.*, g.name AS gear_name, g.brew_method
             FROM filter_pack p
             JOIN user_gear g ON g.id = p.gear_id
            WHERE g.owner_id = ? AND g.kind = 'filter'
              AND p.closed_at IS NULL AND p.remaining > 0
            ORDER BY p.id""",
        (owner_id,),
    ).fetchall()
    return [_pack_public(r) for r in rows]


def pick_pack(
    conn: sqlite3.Connection,
    owner_id: int,
    method: str | None = None,
    pack_id: int | None = None,
) -> dict | None:
    """开着的包只有一包才自动用。多包不自挑。没开包就当没纸。"""
    if method and method not in PAPER_METHODS:
        return None
    if pack_id:
        row = conn.execute(
            """SELECT p.*, g.name AS gear_name, g.brew_method, g.owner_id
                 FROM filter_pack p
                 JOIN user_gear g ON g.id = p.gear_id
                WHERE p.id = ?""",
            (int(pack_id),),
        ).fetchone()
        if not row or row["owner_id"] != owner_id:
            raise HTTPException(404, "没有这包滤纸")
        pack = _pack_public(row)
        if not pack["open"]:
            raise HTTPException(400, "这包已经用完了")
        return pack
    opened = _open_packs(conn, owner_id)
    if method:
        matched = [p for p in opened if not p.get("brew_method") or p["brew_method"] == method]
        if len(matched) == 1:
            return matched[0]
        if len(matched) != 1 and len(opened) != 1:
            return None
    if len(opened) == 1:
        return opened[0]
    return None


def consume_sheet(conn: sqlite3.Connection, pack: dict, sheets: int = 1) -> dict | None:
    if not pack or sheets <= 0:
        return None
    left = int(pack.get("remaining") or 0)
    if left < sheets:
        return None
    new_left = left - sheets
    closed = db.now() if new_left == 0 else None
    conn.execute(
        "UPDATE filter_pack SET remaining = ?, closed_at = ? WHERE id = ?",
        (new_left, closed, pack["id"]),
    )
    return {
        "filter_pack_id": pack["id"],
        "filter_sheets": sheets,
        "filter_unit_cost": pack.get("unit_cost"),
        "sheets_left": new_left,
    }


def restore_sheet(conn: sqlite3.Connection, pack_id: int | None, sheets: int | None) -> None:
    if not pack_id or not sheets:
        return
    row = conn.execute("SELECT * FROM filter_pack WHERE id = ?", (int(pack_id),)).fetchone()
    if not row:
        return
    conn.execute(
        "UPDATE filter_pack SET remaining = remaining + ?, closed_at = NULL WHERE id = ?",
        (int(sheets), pack_id),
    )


def filter_teaser(conn: sqlite3.Connection, owner_id: int | None, method: str | None = None) -> dict | None:
    if not owner_id:
        return None
    opened = _open_packs(conn, owner_id)
    pack = pick_pack(conn, owner_id, method)
    if pack:
        return {
            "pack_id": pack["id"],
            "name": pack.get("gear_name"),
            "remaining": pack["remaining"],
            "unit_cost": pack.get("unit_cost"),
            "sheets": 1,
            "need_pick": False,
        }
    if len(opened) > 1:
        return {
            "need_pick": True,
            "open_count": len(opened),
            "packs": [
                {
                    "pack_id": p["id"],
                    "name": p.get("gear_name"),
                    "remaining": p["remaining"],
                    "unit_cost": p.get("unit_cost"),
                }
                for p in opened
            ],
        }
    return None


def restock_filters(conn: sqlite3.Connection, owner_id: int | None) -> list[dict]:
    """已经开始计张、且用完或只剩不多的滤纸。没开过包的不出现。"""
    if owner_id is None:
        return []
    gears = [g for g in list_gear(conn, owner_id) if g["kind"] == "filter" and g.get("counting")]
    out = []
    for g in gears:
        left = int(g.get("sheets_left") or 0)
        reasons = []
        if left <= 0:
            reasons.append("用完了")
        elif left <= RESTOCK_SHEETS:
            reasons.append(f"只剩 {left} 张")
        if not reasons:
            continue
        last = g["packs"][-1] if g.get("packs") else None
        out.append(
            {
                "id": g["id"],
                "name": g["name"],
                "sheets_left": left,
                "reasons": reasons,
                "last_price": last.get("price") if last else None,
                "cover": g.get("cover"),
            }
        )
    return out
