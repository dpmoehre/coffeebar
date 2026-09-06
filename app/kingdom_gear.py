"""王国器具：复用管理员收录的 gear_catalog，大家评总体分、写一句、收藏。

不另建一种，不套豆子那套八维杯测。领到台面仍走目录拷贝。
"""

from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from . import brew, db, gear, photos
from .kingdom import _author_label, _clean, _score_num


def teaser(conn: sqlite3.Connection, catalog_id: int | None, viewer_id: int | None = None) -> dict | None:
    if not catalog_id:
        return None
    row = conn.execute("SELECT * FROM gear_catalog WHERE id = ?", (catalog_id,)).fetchone()
    if not row:
        return None
    return _brief(conn, row, viewer_id)


def list_kingdom_gear(
    conn: sqlite3.Connection, viewer_id: int | None, *, saved: bool = False
) -> list[dict]:
    rows = conn.execute("SELECT * FROM gear_catalog ORDER BY updated_at DESC, id DESC").fetchall()
    out = [_brief(conn, r, viewer_id) for r in rows]
    if saved:
        out = [g for g in out if g.get("favorited")]
    return out


def get_kingdom_gear(conn: sqlite3.Connection, catalog_id: int, viewer_id: int | None) -> dict | None:
    row = conn.execute("SELECT * FROM gear_catalog WHERE id = ?", (catalog_id,)).fetchone()
    if not row:
        return None
    out = gear._public_catalog(conn, row, owners=True)
    out.pop("collected_by", None)
    out.pop("source_gear_id", None)
    stats = _stats(conn, catalog_id, viewer_id)
    out.update(stats)
    method = out.get("brew_method")
    out["method_label"] = brew.METHODS.get(method) if method else None
    emails = {
        r["id"]: r["email"]
        for r in conn.execute(
            """SELECT a.id, a.email FROM account a
               JOIN kingdom_gear_score s ON s.author_id = a.id WHERE s.catalog_id = ?""",
            (catalog_id,),
        )
    }
    scores = conn.execute(
        "SELECT * FROM kingdom_gear_score WHERE catalog_id = ? ORDER BY updated_at DESC, id DESC",
        (catalog_id,),
    ).fetchall()
    out["scores"] = [
        _score_public(conn, s, email=emails.get(s["author_id"], ""), mine=s["author_id"] == viewer_id)
        for s in scores
    ]
    out["mine"] = next((s for s in out["scores"] if s["mine"]), None)
    out["mine_gear_id"] = _mine_gear_id(conn, catalog_id, viewer_id)
    out["plaza"] = [
        {"id": r["id"], "name": r["name"]}
        for r in conn.execute(
            """SELECT id, name FROM user_gear
                WHERE catalog_id = ? AND visibility = 'public'
                ORDER BY updated_at DESC, id""",
            (catalog_id,),
        ).fetchall()
    ]
    return out


def upsert_score(conn: sqlite3.Connection, catalog_id: int, author_id: int, data: dict) -> dict:
    if not conn.execute("SELECT id FROM gear_catalog WHERE id = ?", (catalog_id,)).fetchone():
        raise HTTPException(404, "王国里没有这件器具")
    overall = _score_num(data.get("overall")) if data.get("overall") not in (None, "") else None
    comment = _clean(data.get("comment"))
    if overall is None and not comment:
        raise HTTPException(400, "至少打一个分，或写一句评价")
    now = db.now()
    existing = conn.execute(
        "SELECT id FROM kingdom_gear_score WHERE catalog_id = ? AND author_id = ?",
        (catalog_id, author_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE kingdom_gear_score SET overall=?, comment=?, updated_at=? WHERE id=?",
            (overall, comment, now, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO kingdom_gear_score
               (catalog_id, author_id, overall, comment, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (catalog_id, author_id, overall, comment, now, now),
        )
    conn.execute("UPDATE gear_catalog SET updated_at = ? WHERE id = ?", (now, catalog_id))
    return get_kingdom_gear(conn, catalog_id, author_id)


def delete_score(conn: sqlite3.Connection, catalog_id: int, author_id: int) -> dict:
    row = conn.execute(
        "SELECT id FROM kingdom_gear_score WHERE catalog_id = ? AND author_id = ?",
        (catalog_id, author_id),
    ).fetchone()
    if row:
        photos.purge_kingdom_gear_score_photos(conn, row["id"])
        conn.execute("DELETE FROM kingdom_gear_score WHERE id = ?", (row["id"],))
    return get_kingdom_gear(conn, catalog_id, author_id)


def add_score_photo(
    conn: sqlite3.Connection, catalog_id: int, author_id: int, raw: bytes, filename: str
) -> dict:
    if not conn.execute("SELECT id FROM gear_catalog WHERE id = ?", (catalog_id,)).fetchone():
        raise HTTPException(404, "王国里没有这件器具")
    score_id = _mine_score_id(conn, catalog_id, author_id)
    photos.attach_kingdom_gear_score_photo(conn, score_id, raw, filename)
    return get_kingdom_gear(conn, catalog_id, author_id)


def delete_score_photo(conn: sqlite3.Connection, photo_id: int, author_id: int) -> dict:
    row = conn.execute(
        """SELECT p.id, s.author_id, s.catalog_id
             FROM kingdom_gear_score_photo p
             JOIN kingdom_gear_score s ON s.id = p.score_id
            WHERE p.id = ?""",
        (photo_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "没有这张图")
    if row["author_id"] != author_id:
        raise HTTPException(403, "只能删自己的图")
    photos.delete_kingdom_gear_score_photo(conn, photo_id)
    return get_kingdom_gear(conn, row["catalog_id"], author_id)


def toggle_favorite(conn: sqlite3.Connection, catalog_id: int, account_id: int) -> dict:
    if not conn.execute("SELECT id FROM gear_catalog WHERE id = ?", (catalog_id,)).fetchone():
        raise HTTPException(404, "王国里没有这件器具")
    hit = conn.execute(
        "SELECT 1 FROM kingdom_gear_favorite WHERE catalog_id = ? AND account_id = ?",
        (catalog_id, account_id),
    ).fetchone()
    if hit:
        conn.execute(
            "DELETE FROM kingdom_gear_favorite WHERE catalog_id = ? AND account_id = ?",
            (catalog_id, account_id),
        )
    else:
        conn.execute(
            "INSERT INTO kingdom_gear_favorite (catalog_id, account_id, created_at) VALUES (?, ?, ?)",
            (catalog_id, account_id, db.now()),
        )
    return get_kingdom_gear(conn, catalog_id, account_id)


def purge_catalog_reviews(conn: sqlite3.Connection, catalog_id: int) -> None:
    rows = conn.execute(
        "SELECT id FROM kingdom_gear_score WHERE catalog_id = ?", (catalog_id,)
    ).fetchall()
    for row in rows:
        photos.purge_kingdom_gear_score_photos(conn, row["id"])


def _mine_gear_id(conn: sqlite3.Connection, catalog_id: int, viewer_id: int | None) -> int | None:
    if not viewer_id:
        return None
    row = conn.execute(
        "SELECT id FROM user_gear WHERE owner_id = ? AND catalog_id = ?",
        (viewer_id, catalog_id),
    ).fetchone()
    return int(row["id"]) if row else None


def _mine_score_id(conn: sqlite3.Connection, catalog_id: int, author_id: int) -> int:
    row = conn.execute(
        "SELECT id FROM kingdom_gear_score WHERE catalog_id = ? AND author_id = ?",
        (catalog_id, author_id),
    ).fetchone()
    if not row:
        raise HTTPException(409, "先记下评价再挂图")
    return int(row["id"])


def _stats(conn: sqlite3.Connection, catalog_id: int, viewer_id: int | None) -> dict:
    scores = conn.execute(
        "SELECT overall FROM kingdom_gear_score WHERE catalog_id = ?", (catalog_id,)
    ).fetchall()
    favs = conn.execute(
        "SELECT COUNT(*) FROM kingdom_gear_favorite WHERE catalog_id = ?", (catalog_id,)
    ).fetchone()[0]
    vals = [r["overall"] for r in scores if r["overall"] is not None]
    favorited = False
    if viewer_id:
        favorited = bool(
            conn.execute(
                "SELECT 1 FROM kingdom_gear_favorite WHERE catalog_id = ? AND account_id = ?",
                (catalog_id, viewer_id),
            ).fetchone()
        )
    return {
        "reviews": len(scores),
        "favorites": int(favs or 0),
        "favorited": favorited,
        "avg": {"overall": round(sum(vals) / len(vals), 2)} if vals else None,
    }


def _brief(conn: sqlite3.Connection, row: sqlite3.Row, viewer_id: int | None) -> dict:
    out = gear._public_catalog(conn, row)
    out.update(_stats(conn, row["id"], viewer_id))
    method = out.get("brew_method")
    out["method_label"] = brew.METHODS.get(method) if method else None
    return out


def _score_public(conn: sqlite3.Connection, row: sqlite3.Row, *, email: str, mine: bool) -> dict:
    return {
        "id": row["id"],
        "overall": row["overall"],
        "comment": row["comment"],
        "at": row["updated_at"] or row["created_at"],
        "author": _author_label(email, mine),
        "mine": mine,
        "photos": photos.list_kingdom_gear_score_photos(conn, row["id"]),
    }
