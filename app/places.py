"""咖啡产地词典：把自由文本产地对上经纬度，不调外网。

匹配规则：按 `&` / `、` 切开（拼配一张卡多个钉），每段取**最具体**的命中
（庄园 > 产区 > 国家）。已有人手点的钉，改产地字符串也不会冲掉。
"""

from __future__ import annotations

import re
import sqlite3

from . import db

# level: 0 国家 / 1 产区 / 2 处理站或庄园
# 坐标取产区中心附近，不是某座农场的测绘点。
_PLACES: list[dict] = [
    # ── 埃塞 ──
    {"key": "ethiopia", "label": "埃塞俄比亚", "lat": 9.15, "lng": 40.49, "level": 0,
     "aliases": ("埃塞俄比亚", "ethiopia", "ethiopian")},
    {"key": "sidama", "label": "埃塞俄比亚 西达玛", "lat": 6.72, "lng": 38.31, "level": 1,
     "aliases": ("西达玛", "sidama", "sidamo")},
    {"key": "yirgacheffe", "label": "埃塞俄比亚 耶加雪菲", "lat": 6.16, "lng": 38.20, "level": 1,
     "aliases": ("耶加雪菲", "yirgacheffe", "yirgachefe", "yega chef")},
    {"key": "guji", "label": "埃塞俄比亚 古吉", "lat": 5.93, "lng": 38.98, "level": 1,
     "aliases": ("古吉", "guji")},
    {"key": "limu", "label": "埃塞俄比亚 利姆", "lat": 8.15, "lng": 36.95, "level": 1,
     "aliases": ("利姆", "limu")},
    {"key": "illubabor", "label": "埃塞俄比亚 伊鲁巴博", "lat": 8.25, "lng": 35.58, "level": 1,
     "aliases": ("伊鲁巴博", "illubabor")},
    {"key": "dimma", "label": "埃塞俄比亚 迪马", "lat": 8.21, "lng": 34.62, "level": 1,
     "aliases": ("迪马", "dimma")},
    {"key": "yaye_testi", "label": "Yaye-Testi 处理站", "lat": 6.68, "lng": 38.42, "level": 2,
     "aliases": ("yaye-testi", "yaye testi", "yaya-testi", "yaya testi")},
    # ── 巴西 ──
    {"key": "brazil", "label": "巴西", "lat": -14.24, "lng": -51.93, "level": 0,
     "aliases": ("巴西", "brazil", "brasil")},
    {"key": "minas", "label": "巴西 米纳斯吉拉斯", "lat": -18.51, "lng": -44.56, "level": 1,
     "aliases": ("米纳斯吉拉斯", "minas gerais")},
    {"key": "sul_de_minas", "label": "巴西 南米纳斯", "lat": -21.25, "lng": -45.00, "level": 1,
     "aliases": ("南米纳斯", "sul de minas", "sul de minas")},
    {"key": "cerrado", "label": "巴西 塞拉多", "lat": -18.92, "lng": -46.99, "level": 1,
     "aliases": ("塞拉多", "cerrado")},
    # ── 哥伦比亚 ──
    {"key": "colombia", "label": "哥伦比亚", "lat": 4.57, "lng": -74.30, "level": 0,
     "aliases": ("哥伦比亚", "colombia")},
    {"key": "huila", "label": "哥伦比亚 蕙兰", "lat": 2.54, "lng": -75.53, "level": 1,
     "aliases": ("蕙兰", "乌伊拉", "huila")},
    {"key": "narino", "label": "哥伦比亚 纳里尼奥", "lat": 1.29, "lng": -77.36, "level": 1,
     "aliases": ("纳里尼奥", "nariño", "narino")},
    {"key": "antioquia", "label": "哥伦比亚 安蒂奥基亚", "lat": 6.25, "lng": -75.57, "level": 1,
     "aliases": ("安蒂奥基亚", "antioquia")},
    # ── 卢旺达 ──
    {"key": "rwanda", "label": "卢旺达", "lat": -1.94, "lng": 29.87, "level": 0,
     "aliases": ("卢旺达", "rwanda")},
    {"key": "ngororero", "label": "卢旺达 恩戈罗雷罗", "lat": -1.86, "lng": 29.63, "level": 1,
     "aliases": ("恩戈罗雷罗", "ngororero")},
    {"key": "matyazo", "label": "Matyazo CWS", "lat": -1.89, "lng": 29.52, "level": 2,
     "aliases": ("matyazo", "matyazo cws")},
    # ── 中美 ──
    {"key": "honduras", "label": "洪都拉斯", "lat": 14.72, "lng": -86.24, "level": 0,
     "aliases": ("洪都拉斯", "honduras")},
    {"key": "francisco_morazan", "label": "洪都拉斯 弗朗西斯科-莫拉桑", "lat": 14.08, "lng": -87.21, "level": 1,
     "aliases": ("弗朗西斯科-莫拉桑", "弗朗西斯科莫拉桑", "francisco morazan", "francisco morazán")},
    {"key": "guatemala", "label": "危地马拉", "lat": 15.50, "lng": -90.25, "level": 0,
     "aliases": ("危地马拉", "guatemala")},
    {"key": "antigua", "label": "危地马拉 安提瓜", "lat": 14.56, "lng": -90.73, "level": 1,
     "aliases": ("安提瓜", "antigua")},
    {"key": "costa_rica", "label": "哥斯达黎加", "lat": 9.75, "lng": -83.75, "level": 0,
     "aliases": ("哥斯达黎加", "costa rica")},
    {"key": "tarrazu", "label": "哥斯达黎加 塔拉珠", "lat": 9.66, "lng": -84.03, "level": 1,
     "aliases": ("塔拉珠", "tarrazu", "tarrazú")},
    {"key": "panama", "label": "巴拿马", "lat": 8.54, "lng": -80.78, "level": 0,
     "aliases": ("巴拿马", "panama")},
    {"key": "boquete", "label": "巴拿马 波克特", "lat": 8.78, "lng": -82.43, "level": 1,
     "aliases": ("波克特", "boquete")},
    {"key": "el_salvador", "label": "萨尔瓦多", "lat": 13.79, "lng": -88.90, "level": 0,
     "aliases": ("萨尔瓦多", "el salvador")},
    {"key": "nicaragua", "label": "尼加拉瓜", "lat": 12.87, "lng": -85.21, "level": 0,
     "aliases": ("尼加拉瓜", "nicaragua")},
    {"key": "mexico", "label": "墨西哥", "lat": 17.50, "lng": -92.50, "level": 0,
     "aliases": ("墨西哥", "mexico", "méxico")},
    # ── 东非 / 也门 ──
    {"key": "kenya", "label": "肯尼亚", "lat": -0.02, "lng": 37.91, "level": 0,
     "aliases": ("肯尼亚", "kenya")},
    {"key": "nyeri", "label": "肯尼亚 涅里", "lat": -0.42, "lng": 36.95, "level": 1,
     "aliases": ("涅里", "nyeri")},
    {"key": "tanzania", "label": "坦桑尼亚", "lat": -6.37, "lng": 34.89, "level": 0,
     "aliases": ("坦桑尼亚", "tanzania")},
    {"key": "uganda", "label": "乌干达", "lat": 1.37, "lng": 32.29, "level": 0,
     "aliases": ("乌干达", "uganda")},
    {"key": "burundi", "label": "布隆迪", "lat": -3.37, "lng": 29.92, "level": 0,
     "aliases": ("布隆迪", "burundi")},
    {"key": "yemen", "label": "也门", "lat": 15.55, "lng": 48.52, "level": 0,
     "aliases": ("也门", "yemen")},
    # ── 亚洲 ──
    {"key": "indonesia", "label": "印度尼西亚", "lat": -0.79, "lng": 113.92, "level": 0,
     "aliases": ("印度尼西亚", "印尼", "indonesia")},
    {"key": "sumatra", "label": "印尼 苏门答腊", "lat": 0.59, "lng": 98.68, "level": 1,
     "aliases": ("苏门答腊", "sumatra")},
    {"key": "java", "label": "印尼 爪哇", "lat": -7.32, "lng": 110.38, "level": 1,
     "aliases": ("爪哇",)},
    {"key": "vietnam", "label": "越南", "lat": 14.06, "lng": 108.28, "level": 0,
     "aliases": ("越南", "vietnam")},
    {"key": "india", "label": "印度", "lat": 15.32, "lng": 75.71, "level": 0,
     "aliases": ("印度", "india")},
    {"key": "yunnan", "label": "中国 云南", "lat": 24.47, "lng": 101.34, "level": 1,
     "aliases": ("云南", "yunnan")},
    {"key": "china", "label": "中国", "lat": 35.86, "lng": 104.20, "level": 0,
     "aliases": ("中国", "china")},
    # ── 其他 ──
    {"key": "peru", "label": "秘鲁", "lat": -9.19, "lng": -75.02, "level": 0,
     "aliases": ("秘鲁", "peru")},
    {"key": "bolivia", "label": "玻利维亚", "lat": -16.29, "lng": -63.59, "level": 0,
     "aliases": ("玻利维亚", "bolivia")},
    {"key": "hawaii", "label": "美国 夏威夷", "lat": 19.90, "lng": -155.58, "level": 1,
     "aliases": ("夏威夷", "kona", "hawaii")},
    {"key": "jamaica", "label": "牙买加", "lat": 18.11, "lng": -77.30, "level": 0,
     "aliases": ("牙买加", "jamaica", "蓝山", "blue mountain")},
]

_SPLIT = re.compile(r"\s*[&＋+]\s*|\s*、\s*|\s+and\s+", re.I)
_BLEND_PREFIX = re.compile(r"^拼配\s*[·.•．.\-—–]?\s*", re.I)
_SPACE = re.compile(r"[\s·.•．，,。/／\\|\-—–_（）()【】\[\]]+")


class Conflict(Exception):
    pass


def _norm(text: str) -> str:
    return _SPACE.sub(" ", (text or "")).strip().lower()


def _has_alias(hay: str, alias: str) -> bool:
    a = _norm(alias)
    if not a:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9 '\-]*", a) and len(a) <= 4:
        return re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", hay) is not None
    return a in hay


def split_origins(origin: str | None) -> list[str]:
    raw = _BLEND_PREFIX.sub("", (origin or "").strip())
    parts = [p.strip() for p in _SPLIT.split(raw) if p.strip()]
    return parts or ([raw] if raw else [])


def match_segment(segment: str) -> dict | None:
    hay = _norm(segment)
    if not hay:
        return None
    best = None
    best_key = (-1, -1)  # level, alias length
    for place in _PLACES:
        for alias in place["aliases"]:
            if not _has_alias(hay, alias):
                continue
            key = (place["level"], len(_norm(alias)))
            if key > best_key:
                best = place
                best_key = key
    return best


def guess(origin: str | None, producer: str | None = None) -> list[dict]:
    """从产地 + 处理厂文本推出一组钉。同一 key 只留一次。"""
    segments = split_origins(origin)
    if producer and producer.strip():
        segments.append(producer.strip())
    seen: set[str] = set()
    out: list[dict] = []
    for seg in segments:
        hit = match_segment(seg)
        if hit and hit["key"] not in seen:
            seen.add(hit["key"])
            out.append(
                {
                    "key": hit["key"],
                    "label": hit["label"],
                    "lat": hit["lat"],
                    "lng": hit["lng"],
                }
            )
    if not out and (origin or producer):
        hit = match_segment(" ".join(x for x in (origin, producer) if x))
        if hit:
            out.append(
                {
                    "key": hit["key"],
                    "label": hit["label"],
                    "lat": hit["lat"],
                    "lng": hit["lng"],
                }
            )
    return out


def list_places(conn: sqlite3.Connection, bean_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT id, lat, lng, label, source FROM bean_place
               WHERE bean_id = ? ORDER BY id""",
            (bean_id,),
        )
    ]


def has_click(conn: sqlite3.Connection, bean_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM bean_place WHERE bean_id = ? AND source = 'click' LIMIT 1",
            (bean_id,),
        ).fetchone()
        is not None
    )


def _insert(conn: sqlite3.Connection, bean_id: int, pins: list[dict], source: str) -> None:
    ts = db.now()
    for p in pins:
        conn.execute(
            """INSERT INTO bean_place (bean_id, lat, lng, label, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bean_id, p["lat"], p["lng"], p.get("label"), source, ts),
        )


def sync_gazetteer(
    conn: sqlite3.Connection, bean_id: int, origin: str | None, producer: str | None
) -> list[dict]:
    """没有手定点时，按文本重写词典钉。有手定点则原样返回。"""
    if has_click(conn, bean_id):
        return list_places(conn, bean_id)
    conn.execute("DELETE FROM bean_place WHERE bean_id = ? AND source = 'gazetteer'", (bean_id,))
    _insert(conn, bean_id, guess(origin, producer), "gazetteer")
    return list_places(conn, bean_id)


def set_click_places(conn: sqlite3.Connection, bean_id: int, pins: list[dict]) -> list[dict]:
    """人手点的一组钉，整表替换（推测钉一起拿掉）。"""
    if not pins:
        raise Conflict("至少点一个位置")
    cleaned = []
    for p in pins:
        try:
            lat = float(p.get("lat"))
            lng = float(p.get("lng"))
        except (TypeError, ValueError) as exc:
            raise Conflict("经纬度要是数字") from exc
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise Conflict("经纬度超出范围")
        cleaned.append(
            {"lat": lat, "lng": lng, "label": (p.get("label") or "手点").strip() or "手点"}
        )
    conn.execute("DELETE FROM bean_place WHERE bean_id = ?", (bean_id,))
    _insert(conn, bean_id, cleaned, "click")
    conn.execute("UPDATE bean SET updated_at = ? WHERE id = ?", (db.now(), bean_id))
    return list_places(conn, bean_id)


def guess_again(
    conn: sqlite3.Connection, bean_id: int, origin: str | None, producer: str | None
) -> list[dict]:
    """清掉手定，按词典重猜。"""
    conn.execute("DELETE FROM bean_place WHERE bean_id = ?", (bean_id,))
    return sync_gazetteer(conn, bean_id, origin, producer)


def backfill(conn: sqlite3.Connection) -> int:
    """老库里还没有落点的豆，启动时补一回词典钉。"""
    rows = conn.execute(
        "SELECT id, origin, producer FROM bean WHERE deleted_at IS NULL"
    ).fetchall()
    n = 0
    for r in rows:
        has = conn.execute(
            "SELECT 1 FROM bean_place WHERE bean_id = ? LIMIT 1", (r["id"],)
        ).fetchone()
        if has:
            continue
        if sync_gazetteer(conn, r["id"], r["origin"], r["producer"]):
            n += 1
    return n


def map_data(conn: sqlite3.Connection, owner_id: int, cover_of) -> dict:
    """给地图页：钉 + 还没定点的豆。cover_of(bean_id) -> 封面或 None。"""
    from . import store  # 函数内导入，避免和 store → places 顶层循环

    beans = conn.execute(
        f"""SELECT b.id, b.name, b.origin, b.roast, b.process, b.producer,
                  (SELECT COUNT(*) FROM bean_lot l
                    WHERE l.bean_id = b.id AND l.closed_at IS NULL) AS open_lots,
                  (SELECT COUNT(*) FROM bean_lot l WHERE l.bean_id = b.id) AS all_lots,
                  COALESCE((SELECT SUM({store.BALANCE}) FROM bean_lot l
                             WHERE l.bean_id = b.id AND l.closed_at IS NULL), 0) AS balance_g
           FROM bean b
           WHERE b.owner_id = ? AND b.deleted_at IS NULL
           ORDER BY b.updated_at DESC""",
        (owner_id,),
    ).fetchall()
    pins: list[dict] = []
    unplaced: list[dict] = []
    for b in beans:
        in_stock = b["open_lots"] > 0
        pending = b["all_lots"] == 0
        info = {
            "id": b["id"],
            "name": b["name"],
            "origin": b["origin"],
            "roast": b["roast"],
            "process": b["process"],
            "producer": b["producer"],
            "tags": store.bean_tags(conn, b["id"]),
            "balance_g": round(float(b["balance_g"] or 0), 1),
            "in_stock": in_stock,
            "pending": pending,
            "cover": cover_of(b["id"]),
        }
        pts = list_places(conn, b["id"])
        if not pts:
            unplaced.append(info)
            continue
        for p in pts:
            pins.append(
                {
                    **info,
                    "bean_id": b["id"],
                    "place_id": p["id"],
                    "lat": p["lat"],
                    "lng": p["lng"],
                    "label": p["label"],
                    "source": p["source"],
                }
            )
    return {"pins": pins, "unplaced": unplaced}
