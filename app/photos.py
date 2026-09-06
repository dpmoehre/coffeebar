"""照片：存盘、转码、缩略图。

豆卡三种都可以缺（见 docs/002）：`pack` 包装袋、`tray` 豆盘、`card` 店家豆卡。
没开封往往只有包装，开封后再补豆盘。豆卡是店家印的参数说明，拍下来留档，
但它不适合当封面（缩略图里一片字），所以 `cover()` 不选它。

冲煮记录另有过程照：`beans` 称豆、`bed` 粉床、`finish` 冲完、`gear` 器具（称盘、壶、滤杯），也都可缺。

手机直出多是 HEIC，浏览器认不了，一律转成 JPEG 存。原图不留——自用场景没必要
占空间，也省得备份包变大。
"""

from __future__ import annotations

import io
import shutil
import sqlite3
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from . import db

try:  # iPhone 直出的 HEIC
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_OK = True
except ImportError:  # 没装也能跑，只是传 HEIC 会被挡下
    HEIC_OK = False

MAX_EDGE = 1600      # 长边上限：吧台屏和手机都够看，不留原始大图
THUMB_EDGE = 900     # 详情页缩略图
LIST_EDGE = 480      # 列表封面：卡片大约 192px，Retina 也够，cpolar 少传一截
QUALITY = 86
MAX_BYTES = 25 * 1024 * 1024


class BadPhoto(Exception):
    pass


def save(raw: bytes, filename: str = "") -> str:
    """存一张图，返回 data/ 下的相对路径（形如 photos/ab12….jpg）。"""
    if not raw:
        raise BadPhoto("空文件")
    if len(raw) > MAX_BYTES:
        raise BadPhoto(f"图太大了（{len(raw) / 1024 / 1024:.0f} MB），限 25 MB")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        suffix = Path(filename).suffix.lower()
        if suffix in {".heic", ".heif"} and not HEIC_OK:
            raise BadPhoto("这是 HEIC，服务器还没装 pillow-heif。先在手机里存成 JPEG，或跑 uv sync")
        raise BadPhoto("这个文件不像图片")

    img = ImageOps.exif_transpose(img)  # 手机竖拍会带旋转信息，先摆正
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

    name = f"{uuid.uuid4().hex}.jpg"
    db.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    img.save(db.PHOTO_DIR / name, "JPEG", quality=QUALITY, optimize=True)

    thumb = img.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.LANCZOS)
    thumb.save(db.PHOTO_DIR / f"t_{name}", "JPEG", quality=80, optimize=True)
    _write_list_thumb(thumb, name)

    return f"photos/{name}"


def remove(rel_path: str) -> None:
    """删文件；缩略图跟着删。文件不在了也不报错。"""
    name = Path(rel_path).name
    for p in (db.PHOTO_DIR / name, db.PHOTO_DIR / f"t_{name}", db.PHOTO_DIR / f"s_{name}"):
        p.unlink(missing_ok=True)


def thumb_url(rel_path: str) -> str:
    return f"/{Path(rel_path).parent}/t_{Path(rel_path).name}"


def _write_list_thumb(img: Image.Image, name: str) -> None:
    small = img.copy()
    if small.mode not in ("RGB", "L"):
        small = small.convert("RGB")
    small.thumbnail((LIST_EDGE, LIST_EDGE), Image.LANCZOS)
    db.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    small.save(db.PHOTO_DIR / f"s_{name}", "JPEG", quality=74, optimize=True)


def ensure_list_thumb(rel_path: str) -> None:
    """老图没有列表封面时补一张。已经有就不动。"""
    name = Path(rel_path).name
    dest = db.PHOTO_DIR / f"s_{name}"
    if dest.exists():
        return
    src = db.PHOTO_DIR / f"t_{name}"
    if not src.exists():
        src = db.PHOTO_DIR / name
    if not src.exists():
        return
    with Image.open(src) as img:
        _write_list_thumb(img, name)


def list_url(rel_path: str) -> str:
    ensure_list_thumb(rel_path)
    return f"/{Path(rel_path).parent}/s_{Path(rel_path).name}"


def with_list(shot: dict | None) -> dict | None:
    """给列表封面补一档更小的图。没有 path 就原样返回。"""
    if not shot or not shot.get("path"):
        return shot
    out = dict(shot)
    out["list"] = list_url(out["path"])
    return out


def attach_bean_photo(conn: sqlite3.Connection, bean_id: int, kind: str, raw: bytes, filename: str) -> dict:
    if kind not in ("pack", "tray", "card"):
        raise BadPhoto("只能是 pack（包装）、tray（豆盘）或 card（豆卡）")
    rel = save(raw, filename)
    cur = conn.execute(
        "INSERT INTO bean_photo (bean_id, kind, path, created_at) VALUES (?, ?, ?, ?)",
        (bean_id, kind, rel, db.now()),
    )
    return {"id": int(cur.lastrowid), "kind": kind, "path": rel, "url": f"/{rel}",
            "thumb": thumb_url(rel)}


def list_bean_photos(conn: sqlite3.Connection, bean_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, kind, path, created_at FROM bean_photo WHERE bean_id = ? ORDER BY created_at",
        (bean_id,),
    ).fetchall()
    return [
        {**dict(r), "url": f"/{r['path']}", "thumb": thumb_url(r["path"])} for r in rows
    ]


def cover(photos: list[dict]) -> dict | None:
    """豆库缩略图优先豆盘，再包装；豆卡缩下去只剩一片字，只在都没有时才用。"""
    if not photos:
        return None
    picked = None
    for kind in ("tray", "pack"):
        hit = [p for p in photos if p["kind"] == kind]
        if hit:
            picked = hit[-1]
            break
    if picked is None:
        picked = photos[-1]
    return with_list(picked)


def delete_bean_photo(conn: sqlite3.Connection, photo_id: int) -> None:
    row = conn.execute("SELECT path FROM bean_photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        raise BadPhoto("没有这张图")
    remove(row["path"])
    conn.execute("DELETE FROM bean_photo WHERE id = ?", (photo_id,))


def attach_bottle_photo(conn: sqlite3.Connection, bottle_id: int, kind: str, raw: bytes, filename: str) -> dict:
    if kind not in ("pack", "label"):
        raise BadPhoto("只能是 pack（瓶盒）或 label（酒标）")
    rel = save(raw, filename)
    cur = conn.execute(
        "INSERT INTO bottle_photo (bottle_id, kind, path, created_at) VALUES (?, ?, ?, ?)",
        (bottle_id, kind, rel, db.now()),
    )
    return {"id": int(cur.lastrowid), "kind": kind, "path": rel, "url": f"/{rel}",
            "thumb": thumb_url(rel)}


def list_bottle_photos(conn: sqlite3.Connection, bottle_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, kind, path, created_at FROM bottle_photo WHERE bottle_id = ? ORDER BY created_at",
        (bottle_id,),
    ).fetchall()
    return [
        {**dict(r), "url": f"/{r['path']}", "thumb": thumb_url(r["path"])} for r in rows
    ]


def delete_bottle_photo(conn: sqlite3.Connection, photo_id: int) -> None:
    row = conn.execute("SELECT path FROM bottle_photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        raise BadPhoto("没有这张图")
    remove(row["path"])
    conn.execute("DELETE FROM bottle_photo WHERE id = ?", (photo_id,))


BREW_PHOTO_KINDS = ("beans", "bed", "finish", "gear")


def attach_consumption_photo(
    conn: sqlite3.Connection, cons_id: int, kind: str, raw: bytes, filename: str
) -> dict:
    if kind not in BREW_PHOTO_KINDS:
        raise BadPhoto("只能是 beans（称豆）、bed（粉床）、finish（冲完）或 gear（器具）")
    row = conn.execute("SELECT id FROM consumption_event WHERE id = ?", (cons_id,)).fetchone()
    if not row:
        raise BadPhoto("没有这笔冲煮")
    rel = save(raw, filename)
    cur = conn.execute(
        "INSERT INTO consumption_photo (cons_id, kind, path, created_at) VALUES (?, ?, ?, ?)",
        (cons_id, kind, rel, db.now()),
    )
    return {
        "id": int(cur.lastrowid),
        "cons_id": cons_id,
        "kind": kind,
        "path": rel,
        "url": f"/{rel}",
        "thumb": thumb_url(rel),
    }


def list_consumption_photos(conn: sqlite3.Connection, cons_ids: list[int]) -> dict[int, list[dict]]:
    """按消耗 id 分组。空列表直接返回。"""
    if not cons_ids:
        return {}
    q = ",".join("?" * len(cons_ids))
    rows = conn.execute(
        f"SELECT id, cons_id, kind, path, created_at FROM consumption_photo "
        f"WHERE cons_id IN ({q}) ORDER BY created_at, id",
        cons_ids,
    ).fetchall()
    out: dict[int, list[dict]] = {i: [] for i in cons_ids}
    for r in rows:
        out[r["cons_id"]].append(
            {**dict(r), "url": f"/{r['path']}", "thumb": thumb_url(r["path"])}
        )
    return out


def delete_consumption_photo(conn: sqlite3.Connection, photo_id: int) -> None:
    row = conn.execute("SELECT path FROM consumption_photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        raise BadPhoto("没有这张图")
    remove(row["path"])
    conn.execute("DELETE FROM consumption_photo WHERE id = ?", (photo_id,))


def purge_consumption_photos(conn: sqlite3.Connection, cons_id: int) -> int:
    """删掉一笔消耗上的过程照文件和行。删记录前调用，避免盘上留下孤儿图。"""
    rows = conn.execute(
        "SELECT id, path FROM consumption_photo WHERE cons_id = ?", (cons_id,)
    ).fetchall()
    for r in rows:
        remove(r["path"])
        conn.execute("DELETE FROM consumption_photo WHERE id = ?", (r["id"],))
    return len(rows)


def paths_for_bottle(conn: sqlite3.Connection, bottle_id: int) -> list[str]:
    """一支酒名下所有照片路径：瓶盒 / 酒标、各瓶流水的过程照。"""
    rows = conn.execute(
        """
        SELECT path FROM bottle_photo WHERE bottle_id = ?
        UNION ALL
        SELECT path FROM consumption_photo
         WHERE cons_id IN (
           SELECT c.id FROM consumption_event c
           JOIN bottle_lot l ON l.id = c.bottle_lot_id
           WHERE l.bottle_id = ?
         )
        """,
        (bottle_id, bottle_id),
    ).fetchall()
    return [r["path"] for r in rows]


def paths_for_bean(conn: sqlite3.Connection, bean_id: int) -> list[str]:
    """一支豆名下所有照片路径：包装/豆盘/豆卡、补货对照图、各袋流水的过程照。"""
    rows = conn.execute(
        """
        SELECT path FROM bean_photo WHERE bean_id = ?
        UNION ALL
        SELECT path FROM restock_photo WHERE bean_id = ?
        UNION ALL
        SELECT path FROM consumption_photo
         WHERE cons_id IN (
           SELECT c.id FROM consumption_event c
           JOIN bean_lot l ON l.id = c.lot_id
           WHERE l.bean_id = ?
         )
        """,
        (bean_id, bean_id, bean_id),
    ).fetchall()
    return [r["path"] for r in rows]


def paths_for_owner(conn: sqlite3.Connection, owner_id: int) -> list[str]:
    """这个账号名下所有照片路径，注销时先收齐再删文件。"""
    rows = conn.execute(
        """
        SELECT path FROM bean_photo
         WHERE bean_id IN (SELECT id FROM bean WHERE owner_id = ?)
        UNION ALL
        SELECT path FROM restock_photo
         WHERE bean_id IN (SELECT id FROM bean WHERE owner_id = ?)
        UNION ALL
        SELECT path FROM bottle_photo
         WHERE bottle_id IN (SELECT id FROM bottle WHERE owner_id = ?)
        UNION ALL
        SELECT path FROM consumption_photo
         WHERE cons_id IN (
           SELECT c.id FROM consumption_event c
           LEFT JOIN bean_lot l ON l.id = c.lot_id
           LEFT JOIN bean b ON b.id = l.bean_id
           LEFT JOIN bottle_lot bl ON bl.id = c.bottle_lot_id
           LEFT JOIN bottle sp ON sp.id = bl.bottle_id
           WHERE b.owner_id = ? OR sp.owner_id = ?
         )
        UNION ALL
        SELECT path FROM user_gear_photo
         WHERE gear_id IN (SELECT id FROM user_gear WHERE owner_id = ?)
        UNION ALL
        SELECT path FROM kingdom_score_photo
         WHERE score_id IN (SELECT id FROM kingdom_score WHERE author_id = ?)
        """,
        (owner_id, owner_id, owner_id, owner_id, owner_id, owner_id, owner_id),
    ).fetchall()
    return [r["path"] for r in rows]


def copy_file(rel_path: str) -> str:
    """复制一张已入库的图（连缩略图），给管理员收录用。原图还在主人那边。"""
    name = Path(rel_path).name
    src = db.PHOTO_DIR / name
    if not src.exists():
        raise BadPhoto("原图不在了")
    new = f"{uuid.uuid4().hex}.jpg"
    shutil.copy2(src, db.PHOTO_DIR / new)
    thumb = db.PHOTO_DIR / f"t_{name}"
    if thumb.exists():
        shutil.copy2(thumb, db.PHOTO_DIR / f"t_{new}")
    small = db.PHOTO_DIR / f"s_{name}"
    if small.exists():
        shutil.copy2(small, db.PHOTO_DIR / f"s_{new}")
    else:
        ensure_list_thumb(f"photos/{new}")
    return f"photos/{new}"


def attach_gear_photo(conn: sqlite3.Connection, gear_id: int, raw: bytes, filename: str) -> dict:
    rel = save(raw, filename)
    cur = conn.execute(
        "INSERT INTO user_gear_photo (gear_id, path, created_at) VALUES (?, ?, ?)",
        (gear_id, rel, db.now()),
    )
    return {
        "id": int(cur.lastrowid),
        "gear_id": gear_id,
        "path": rel,
        "url": f"/{rel}",
        "thumb": thumb_url(rel),
    }


def delete_gear_photo(conn: sqlite3.Connection, photo_id: int) -> None:
    row = conn.execute("SELECT path FROM user_gear_photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        raise BadPhoto("没有这张图")
    remove(row["path"])
    conn.execute("DELETE FROM user_gear_photo WHERE id = ?", (photo_id,))


def purge_gear_photos(conn: sqlite3.Connection, gear_id: int) -> int:
    rows = conn.execute(
        "SELECT id, path FROM user_gear_photo WHERE gear_id = ?", (gear_id,)
    ).fetchall()
    for r in rows:
        remove(r["path"])
        conn.execute("DELETE FROM user_gear_photo WHERE id = ?", (r["id"],))
    return len(rows)


SCORE_PHOTO_LIMIT = 8


def list_kingdom_score_photos(conn: sqlite3.Connection, score_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, path, created_at FROM kingdom_score_photo WHERE score_id = ? ORDER BY created_at, id",
        (score_id,),
    ).fetchall()
    return [
        {**dict(r), "url": f"/{r['path']}", "thumb": thumb_url(r["path"])} for r in rows
    ]


def attach_kingdom_score_photo(
    conn: sqlite3.Connection, score_id: int, raw: bytes, filename: str
) -> dict:
    n = conn.execute(
        "SELECT COUNT(*) FROM kingdom_score_photo WHERE score_id = ?", (score_id,)
    ).fetchone()[0]
    if n >= SCORE_PHOTO_LIMIT:
        raise BadPhoto(f"一杯最多 {SCORE_PHOTO_LIMIT} 张")
    rel = save(raw, filename)
    cur = conn.execute(
        "INSERT INTO kingdom_score_photo (score_id, path, created_at) VALUES (?, ?, ?)",
        (score_id, rel, db.now()),
    )
    return {
        "id": int(cur.lastrowid),
        "score_id": score_id,
        "path": rel,
        "url": f"/{rel}",
        "thumb": thumb_url(rel),
    }


def delete_kingdom_score_photo(conn: sqlite3.Connection, photo_id: int) -> None:
    row = conn.execute("SELECT path FROM kingdom_score_photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        raise BadPhoto("没有这张图")
    remove(row["path"])
    conn.execute("DELETE FROM kingdom_score_photo WHERE id = ?", (photo_id,))


def purge_kingdom_score_photos(conn: sqlite3.Connection, score_id: int) -> int:
    rows = conn.execute(
        "SELECT id, path FROM kingdom_score_photo WHERE score_id = ?", (score_id,)
    ).fetchall()
    for r in rows:
        remove(r["path"])
        conn.execute("DELETE FROM kingdom_score_photo WHERE id = ?", (r["id"],))
    return len(rows)


def copy_to_bean(conn: sqlite3.Connection, bean_id: int, kind: str, rel_path: str) -> dict | None:
    """广场领回：拷一张豆卡图到自己的卡上。"""
    try:
        copied = copy_file(rel_path)
    except BadPhoto:
        return None
    if kind not in ("pack", "tray", "card"):
        kind = "pack"
    cur = conn.execute(
        "INSERT INTO bean_photo (bean_id, kind, path, created_at) VALUES (?, ?, ?, ?)",
        (bean_id, kind, copied, db.now()),
    )
    return {
        "id": int(cur.lastrowid),
        "bean_id": bean_id,
        "kind": kind,
        "path": copied,
        "url": f"/{copied}",
        "thumb": thumb_url(copied),
    }


def copy_to_user_gear(conn: sqlite3.Connection, gear_id: int, rel_path: str) -> dict | None:
    """广场领回：拷一张器具图到自己台面。"""
    try:
        copied = copy_file(rel_path)
    except BadPhoto:
        return None
    cur = conn.execute(
        "INSERT INTO user_gear_photo (gear_id, path, created_at) VALUES (?, ?, ?)",
        (gear_id, copied, db.now()),
    )
    return {
        "id": int(cur.lastrowid),
        "gear_id": gear_id,
        "path": copied,
        "url": f"/{copied}",
        "thumb": thumb_url(copied),
    }


def copy_to_kingdom(conn: sqlite3.Connection, kingdom_id: int, rel_path: str) -> dict | None:
    try:
        copied = copy_file(rel_path)
    except BadPhoto:
        return None
    cur = conn.execute(
        "INSERT INTO kingdom_photo (kingdom_id, path, created_at) VALUES (?, ?, ?)",
        (kingdom_id, copied, db.now()),
    )
    return {
        "id": int(cur.lastrowid),
        "kingdom_id": kingdom_id,
        "path": copied,
        "url": f"/{copied}",
        "thumb": thumb_url(copied),
    }


def copy_to_catalog(conn: sqlite3.Connection, catalog_id: int, rel_path: str) -> dict | None:
    try:
        copied = copy_file(rel_path)
    except BadPhoto:
        return None
    cur = conn.execute(
        "INSERT INTO gear_catalog_photo (catalog_id, path, created_at) VALUES (?, ?, ?)",
        (catalog_id, copied, db.now()),
    )
    return {
        "id": int(cur.lastrowid),
        "catalog_id": catalog_id,
        "path": copied,
        "url": f"/{copied}",
        "thumb": thumb_url(copied),
    }


def attach_restock_photo(conn: sqlite3.Connection, bean_id: int, raw: bytes, filename: str,
                         note: str | None = None) -> dict:
    """补货条目的对照图：货架、截图、上次那袋都行。"""
    rel = save(raw, filename)
    cur = conn.execute(
        "INSERT INTO restock_photo (bean_id, path, note, created_at) VALUES (?, ?, ?, ?)",
        (bean_id, rel, note, db.now()),
    )
    return {"id": int(cur.lastrowid), "path": rel, "url": f"/{rel}", "thumb": thumb_url(rel)}
