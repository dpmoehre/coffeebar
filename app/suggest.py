"""从在库豆给一个人指出下一杯。只读，不记消耗。"""

from __future__ import annotations

from datetime import date, timedelta

from . import db, freshness, photos, store

RECENT_CUPS = 20
RECENT_DAYS = 3
REPEAT_PENALTY = 30
NEVER_BONUS = 6
ORIGIN_BONUS = 5
PROCESS_BONUS = 5

PHASE_POINTS = {
    "peak": 12,
    "resting": 4,
    "fading": 4,
    "unknown": 0,
    "stale": -8,
}

_NOTE_TIE = "在库这几支暂时分不出先后"


def for_person(
    conn,
    person_id: int,
    *,
    taste: dict,
    enough_sample: bool,
    owner_id: int | None,
) -> dict | None:
    """enough_sample 为假则 None；否则 {primary, alternates, note?}。"""
    if not enough_sample:
        return None

    recent = _recent_cups(conn, person_id)
    recent_ids = {row["bean_id"] for row in recent}
    drunk_ids = _drunk_bean_ids(conn, person_id)
    recent_days = _recent_business_days()
    recent_repeat = _beans_on_days(conn, person_id, recent_days)

    roast_counts: dict[tuple[int, int, int], int] = {}
    origins: list[str] = []
    processes: list[str] = []
    for row in recent:
        key = freshness.window(row.get("roast"))
        roast_counts[key] = roast_counts.get(key, 0) + 1
        if row.get("origin"):
            origins.append(row["origin"])
        if row.get("process"):
            processes.append(row["process"])
    n = len(recent) or 1

    scored: list[dict] = []
    for bean in store.list_beans(conn, "stock", owner_id=owner_id):
        if not bean.get("in_stock") or (bean.get("balance_g") or 0) <= 0:
            continue
        cand = _score_bean(
            conn,
            bean,
            taste=taste,
            roast_counts=roast_counts,
            roast_n=n,
            origins=origins,
            processes=processes,
            never=bean["id"] not in drunk_ids,
            recent_repeat=bean["id"] in recent_repeat,
            seen_recently=bean["id"] in recent_ids,
        )
        if cand:
            scored.append(cand)

    if not scored:
        return {"primary": None, "alternates": [], "note": _NOTE_TIE}

    scored.sort(key=lambda x: (-x["score"], -x["balance_g"], x["name"]))
    open_pool = [x for x in scored if not x["recent_repeat"]]
    if not open_pool:
        return {"primary": None, "alternates": [], "note": _NOTE_TIE}

    primary = _public_item(open_pool[0])
    rest = [x for x in scored if x["bean_id"] != primary["bean_id"]]
    alternates = [_public_item(x) for x in rest[:2]]
    return {"primary": primary, "alternates": alternates}


def _public_item(row: dict) -> dict:
    return {
        "bean_id": row["bean_id"],
        "name": row["name"],
        "reason": row["reason"],
        "phase": row["phase"],
        "cover": row.get("cover"),
    }


def _score_bean(
    conn,
    bean: dict,
    *,
    taste: dict,
    roast_counts: dict,
    roast_n: int,
    origins: list[str],
    processes: list[str],
    never: bool,
    recent_repeat: bool,
    seen_recently: bool,
) -> dict | None:
    roast_key = freshness.window(bean.get("roast"))
    roast_share = roast_counts.get(roast_key, 0) / roast_n
    taste_pts, taste_bits = _taste_points(taste, bean.get("scores"))
    origin_hit = bool(bean.get("origin") and any(store._text_like(bean["origin"], o) for o in origins))
    process_hit = bool(
        bean.get("process") and any(store._text_like(bean["process"], p) for p in processes)
    )
    fresh = bean.get("freshness") or {}
    phase = fresh.get("phase") or "unknown"

    score = roast_share * 20
    score += taste_pts
    if origin_hit:
        score += ORIGIN_BONUS
    if process_hit:
        score += PROCESS_BONUS
    score += PHASE_POINTS.get(phase, 0)
    if recent_repeat:
        score -= REPEAT_PENALTY
    elif never:
        score += NEVER_BONUS

    reason = _reason(
        roast_share=roast_share,
        roast=bean.get("roast"),
        taste=taste,
        taste_bits=taste_bits,
        origin_hit=origin_hit,
        process_hit=process_hit,
        phase=phase,
        never=never,
        recent_repeat=recent_repeat,
        seen_recently=seen_recently,
    )
    if not reason:
        return None

    return {
        "bean_id": bean["id"],
        "name": bean["name"],
        "reason": reason,
        "phase": phase,
        "cover": photos.cover(photos.list_bean_photos(conn, bean["id"])),
        "score": score,
        "balance_g": float(bean.get("balance_g") or 0),
        "recent_repeat": recent_repeat,
    }


def _taste_points(profile: dict, scores: dict | None) -> tuple[float, list[str]]:
    if not scores:
        return 0.0, []
    bits = []
    vals = []
    for key, label in (("acidity", "酸质"), ("sweetness", "甜感"), ("dry", "干香")):
        p = profile.get(key) if profile else None
        b = scores.get(key)
        if p is None or b is None:
            continue
        closeness = max(0.0, 10 - abs(float(p) - float(b))) / 10
        vals.append(closeness)
        if closeness >= 0.7:
            bits.append(label)
    if not vals:
        return 0.0, []
    return (sum(vals) / len(vals)) * 20, bits


def _reason(
    *,
    roast_share: float,
    roast: str | None,
    taste: dict,
    taste_bits: list[str],
    origin_hit: bool,
    process_hit: bool,
    phase: str,
    never: bool,
    recent_repeat: bool,
    seen_recently: bool,
) -> str:
    lead = []
    if roast_share >= 0.35:
        lead.append(_roast_word(roast))
    if (taste or {}).get("acidity") is not None and taste["acidity"] >= 6.5:
        lead.append("高酸")
    person = []
    if lead:
        person.append("近几杯" + "".join(lead) + "多")
    elif taste_bits:
        person.append(f"{'、'.join(taste_bits)}接近他的口味")

    bean = []
    if phase == "peak":
        bean.append("这支正当时")
    elif phase == "resting":
        bean.append("这支还在养豆")
    if origin_hit:
        bean.append("产地他对得上")
    if process_hit:
        bean.append("处理法也喝过")
    if never:
        bean.append("还没给他冲过")
    elif not recent_repeat and seen_recently:
        bean.append("这几天没喝过")
    elif recent_repeat:
        bean.append("不过这几天刚喝过")

    bits = person + bean
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0] + "。"
    return "，".join(bits[:-1]) + "，" + bits[-1] + "。"


def _roast_word(roast: str | None) -> str:
    rest, _, _ = freshness.window(roast)
    if rest == freshness.WINDOW_LIGHT:
        return "浅烘"
    if rest == freshness.WINDOW_MEDIUM_DARK:
        return "中深烘"
    if rest == freshness.WINDOW_DARK:
        return "深烘"
    return "中烘"


def _recent_cups(conn, person_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT l.bean_id, b.name, b.roast, b.origin, b.process
               FROM consumption_event c
               JOIN bean_lot l ON l.id = c.lot_id
               JOIN bean b ON b.id = l.bean_id
               WHERE c.voided_at IS NULL AND c.kind = 'coffee' AND c.person_id = ?
                 AND COALESCE(c.as_cup, 1) = 1
               ORDER BY c.at DESC, c.id DESC LIMIT ?""",
            (person_id, RECENT_CUPS),
        ).fetchall()
    ]


def _drunk_bean_ids(conn, person_id: int) -> set[int]:
    rows = conn.execute(
        """SELECT DISTINCT l.bean_id
           FROM consumption_event c
           JOIN bean_lot l ON l.id = c.lot_id
           WHERE c.voided_at IS NULL AND c.kind = 'coffee' AND c.person_id = ?
             AND COALESCE(c.as_cup, 1) = 1""",
        (person_id,),
    ).fetchall()
    return {int(r[0]) for r in rows}


def _beans_on_days(conn, person_id: int, days: set[str]) -> set[int]:
    if not days:
        return set()
    rows = conn.execute(
        """SELECT l.bean_id, c.at
           FROM consumption_event c
           JOIN bean_lot l ON l.id = c.lot_id
           WHERE c.voided_at IS NULL AND c.kind = 'coffee' AND c.person_id = ?
             AND COALESCE(c.as_cup, 1) = 1""",
        (person_id,),
    ).fetchall()
    out = set()
    for bean_id, at in rows:
        if at and db.business_day(at) in days:
            out.add(int(bean_id))
    return out


def _recent_business_days() -> set[str]:
    today = date.fromisoformat(db.business_day(db.now()))
    return {(today - timedelta(days=i)).isoformat() for i in range(RECENT_DAYS)}
