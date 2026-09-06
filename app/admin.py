"""管理员看所有人的私库。普通人接口仍然按 owner 隔离。"""

from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from . import auth, db, photos, places, spirits, stats, store


def _public(row: sqlite3.Row | dict) -> dict:
    out = auth.public_account(row)
    out["status"] = row["status"]
    out["created_at"] = row["created_at"]
    return out


def list_accounts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, email, email_verified, created_at, status FROM account ORDER BY id"
    ).fetchall()
    out = []
    for row in rows:
        d = _public(row)
        aid = d["id"]
        d["beans"] = conn.execute(
            "SELECT COUNT(*) FROM bean WHERE owner_id = ? AND deleted_at IS NULL", (aid,)
        ).fetchone()[0]
        d["spirits"] = conn.execute(
            "SELECT COUNT(*) FROM bottle WHERE owner_id = ? AND deleted_at IS NULL", (aid,)
        ).fetchone()[0]
        d["people"] = conn.execute(
            "SELECT COUNT(*) FROM person WHERE owner_id = ?", (aid,)
        ).fetchone()[0]
        summary = stats.summary(conn, "all", owner_id=aid)
        d["spent"] = summary.get("spent")
        d["bought"] = summary.get("bought")
        d["cups"] = summary.get("cups")
        d["drink_cups"] = summary.get("drink_cups")
        out.append(d)
    return out


def get_account(conn: sqlite3.Connection, account_id: int) -> dict:
    row = conn.execute("SELECT * FROM account WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "没有这个账号")
    return _public(row)


def dossier(conn: sqlite3.Connection, account_id: int) -> dict:
    account = get_account(conn, account_id)
    beans = store.list_beans(conn, "all", owner_id=account_id)
    bottles = spirits.list_spirits(conn, "all", owner_id=account_id)
    people = store.list_people(conn, include_inactive=True, owner_id=account_id)
    log = store.list_consumption(conn, owner_id=account_id, limit=80)
    return {
        "account": account,
        "summary": stats.summary(conn, "all", owner_id=account_id),
        "beans": beans,
        "spirits": bottles,
        "people": people,
        "consumption": log,
    }


def bean_detail(conn: sqlite3.Connection, account_id: int, bean_id: int) -> dict:
    get_account(conn, account_id)
    bean = store.get_bean(conn, bean_id, owner_id=account_id)
    if not bean:
        raise HTTPException(404, "没有这支豆")
    dose = stats.average_dose(conn, bean_id)
    bean["photos"] = photos.list_bean_photos(conn, bean_id)
    bean["avg_dose"] = dose
    bean["cups_left"] = stats.cups_left(bean["balance_g"], dose["avg_g"])
    bean["log"] = store.list_consumption(conn, bean_id=bean_id, owner_id=account_id, limit=40)
    return bean


def spirit_detail(conn: sqlite3.Connection, account_id: int, bottle_id: int) -> dict:
    get_account(conn, account_id)
    bottle = spirits.get_spirit(conn, bottle_id, owner_id=account_id)
    if not bottle:
        raise HTTPException(404, "没有这支酒")
    bottle["photos"] = photos.list_bottle_photos(conn, bottle_id)
    bottle["log"] = store.list_consumption(conn, bottle_id=bottle_id, owner_id=account_id, limit=40)
    return bottle


def set_status(conn: sqlite3.Connection, actor: dict, account_id: int, status: str) -> dict:
    if status not in ("active", "disabled"):
        raise HTTPException(400, "只能是 active 或 disabled")
    row = conn.execute("SELECT * FROM account WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "没有这个账号")
    if row["id"] == actor["id"]:
        raise HTTPException(400, "不能停用自己")
    if auth.is_admin_email(row["email"]) and status == "disabled":
        raise HTTPException(400, "不能停用管理员")
    conn.execute("UPDATE account SET status = ? WHERE id = ?", (status, account_id))
    if status == "disabled":
        auth.drop_all_sessions(conn, account_id)
    return get_account(conn, account_id)


def kick(conn: sqlite3.Connection, actor: dict, account_id: int) -> dict:
    row = conn.execute("SELECT * FROM account WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "没有这个账号")
    if row["id"] == actor["id"]:
        raise HTTPException(400, "不能把自己踢下线")
    auth.drop_all_sessions(conn, account_id)
    return {"ok": True}


def _bean_row(conn: sqlite3.Connection, bean_id: int) -> dict:
    row = conn.execute("SELECT * FROM bean WHERE id = ? AND deleted_at IS NULL", (bean_id,)).fetchone()
    if not row:
        raise HTTPException(404, "没有这支豆")
    return dict(row)


SCORE_DIMS = ("dry", "flavor", "aftertaste", "acidity", "sweetness", "body", "balance", "overall")


def _has_cupping(score: dict | None) -> bool:
    if not score:
        return False
    if (score.get("comment") or "").strip():
        return True
    return any(score.get(k) is not None for k in SCORE_DIMS)


def review_price(conn: sqlite3.Connection, bean_id: int) -> dict | None:
    """审核只看买袋价，不带剩余和谁喝的。"""
    row = conn.execute(
        """SELECT price, nominal_g, measured_g, bought_on
             FROM bean_lot
            WHERE bean_id = ? AND price IS NOT NULL
            ORDER BY created_at DESC, id DESC
            LIMIT 1""",
        (bean_id,),
    ).fetchone()
    if not row:
        return None
    usable = row["measured_g"] if row["measured_g"] else row["nominal_g"]
    bags = conn.execute(
        "SELECT COUNT(*) FROM bean_lot WHERE bean_id = ? AND price IS NOT NULL",
        (bean_id,),
    ).fetchone()[0]
    return {
        "price": row["price"],
        "nominal_g": row["nominal_g"],
        "bought_on": row["bought_on"],
        "bags": bags,
        "unit_cost": (row["price"] / usable) if row["price"] and usable else None,
    }


def review_checklist(
    *,
    photos_ok: bool,
    scores,
    note,
    price,
    origin,
    places_info,
) -> dict:
    current = (places_info or {}).get("current") if isinstance(places_info, dict) else None
    return {
        "photos": bool(photos_ok),
        "scores": _has_cupping(scores),
        "note": bool((note or "").strip()),
        "price": bool(price),
        "origin": bool((origin or "").strip()),
        "places": bool(current),
    }


def review_queue(conn: sqlite3.Connection, status: str = "pending") -> list[dict]:
    where = "b.visibility = 'public' AND b.deleted_at IS NULL"
    if status == "pending":
        where += " AND b.certified_at IS NULL"
    elif status == "certified":
        where += " AND b.certified_at IS NOT NULL"
    elif status != "public":
        raise HTTPException(400, "status 只能是 pending / certified / public")
    rows = conn.execute(
        f"""SELECT b.id, b.name, b.origin, b.varietal, b.producer, b.process, b.roast,
                   b.note, b.visibility, b.certified_at, b.certified_by, b.review_note,
                   b.places_verified_at, b.updated_at, b.owner_id,
                   a.email AS owner_email
              FROM bean b
              LEFT JOIN account a ON a.id = b.owner_id
             WHERE {where}
             ORDER BY (b.certified_at IS NULL) DESC, b.updated_at DESC""",
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        shots = photos.list_bean_photos(conn, d["id"])
        scores = store.latest_score(conn, d["id"])
        price = review_price(conn, d["id"])
        d["certified"] = bool(d.get("certified_at"))
        d["places"] = places.review_places(conn, d["id"], d.get("origin"), d.get("producer"))
        d["cover"] = photos.cover(shots)
        d["photo_count"] = len(shots)
        d["price"] = price
        d["checklist"] = review_checklist(
            photos_ok=bool(shots),
            scores=scores,
            note=d.get("note"),
            price=price,
            origin=d.get("origin"),
            places_info=d["places"],
        )
        out.append(d)
    return out


def review_bean(conn: sqlite3.Connection, bean_id: int) -> dict:
    bean = _bean_row(conn, bean_id)
    if (bean.get("visibility") or "private") != "public":
        raise store.Conflict("这张卡还没公开，不用审")
    owner = conn.execute(
        "SELECT id, email FROM account WHERE id = ?", (bean.get("owner_id"),)
    ).fetchone()
    shots = photos.list_bean_photos(conn, bean_id)
    scores = store.latest_score(conn, bean_id)
    price = review_price(conn, bean_id)
    pins = places.review_places(conn, bean_id, bean.get("origin"), bean.get("producer"))
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
        "certified_by": bean.get("certified_by"),
        "review_note": bean.get("review_note"),
        "places_verified_at": bean.get("places_verified_at"),
        "updated_at": bean.get("updated_at"),
        "owner": {"id": owner["id"], "email": owner["email"]} if owner else None,
        "tags": store.bean_tags(conn, bean_id),
        "scores": scores,
        "photos": shots,
        "cover": photos.cover(shots),
        "photo_count": len(shots),
        "price": price,
        "places": pins,
        "checklist": review_checklist(
            photos_ok=bool(shots),
            scores=scores,
            note=bean.get("note"),
            price=price,
            origin=bean.get("origin"),
            places_info=pins,
        ),
    }


def certify_bean(
    conn: sqlite3.Connection,
    actor: dict,
    bean_id: int,
    *,
    note: str = "",
    verify_places: bool = True,
    force_places: bool = False,
) -> dict:
    bean = _bean_row(conn, bean_id)
    if (bean.get("visibility") or "private") != "public":
        raise store.Conflict("先让主人把这张卡公开，才能认证")
    check = places.review_places(conn, bean_id, bean.get("origin"), bean.get("producer"))
    if verify_places and check["warnings"] and not force_places:
        raise store.Conflict(
            "地图落点还没对上："
            + "；".join(check["warnings"])
            + "。先 review_set_places / review_guess_places，或带 force_places",
            extra={"places": check},
        )
    now = db.now()
    conn.execute(
        """UPDATE bean
              SET certified_at = ?, certified_by = ?, review_note = ?,
                  places_verified_at = ?, updated_at = ?
            WHERE id = ?""",
        (now, actor["id"], (note or "").strip() or None, now, now, bean_id),
    )
    return review_bean(conn, bean_id)


def uncertify_bean(conn: sqlite3.Connection, actor: dict, bean_id: int, note: str = "") -> dict:
    _bean_row(conn, bean_id)
    now = db.now()
    conn.execute(
        """UPDATE bean
              SET certified_at = NULL, certified_by = NULL,
                  places_verified_at = NULL, review_note = ?, updated_at = ?
            WHERE id = ?""",
        ((note or "").strip() or "取消认证", now, bean_id),
    )
    return review_bean(conn, bean_id)


def review_set_places(conn: sqlite3.Connection, bean_id: int, pins: list) -> dict:
    bean = _bean_row(conn, bean_id)
    if (bean.get("visibility") or "private") != "public":
        raise store.Conflict("这张卡还没公开，不用审")
    try:
        places.set_click_places(conn, bean_id, pins)
    except places.Conflict as exc:
        raise store.Conflict(str(exc)) from exc
    return review_bean(conn, bean_id)


def review_guess_places(conn: sqlite3.Connection, bean_id: int) -> dict:
    bean = _bean_row(conn, bean_id)
    if (bean.get("visibility") or "private") != "public":
        raise store.Conflict("这张卡还没公开，不用审")
    places.guess_again(conn, bean_id, bean.get("origin"), bean.get("producer"))
    return review_bean(conn, bean_id)
