"""赏味窗口：只算，不落库。

烘焙日在袋子上。改烘焙日或烘焙度，阶段当场变。
杯测要自己冻一份天数和阶段，不要来读这里的现算结果。
"""

from __future__ import annotations

import re
from datetime import date

LABELS = {
    "unknown": "没填烘焙日",
    "resting": "养豆中",
    "peak": "正当时",
    "fading": "过了高峰",
    "stale": "老了",
}

# 养豆结束（不含） / 正当时结束（不含） / 老了（含）
WINDOW_LIGHT = (10, 28, 56)
WINDOW_MEDIUM = (7, 21, 42)
WINDOW_MEDIUM_DARK = (5, 18, 35)
WINDOW_DARK = (4, 14, 28)

OPENED_LONG_AFTER = 14

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def calendar_today() -> str:
    return date.today().isoformat()


def parse_date(value, *, field: str = "烘焙日") -> str | None:
    """空着就算没填。只接受 YYYY-MM-DD。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not _DATE.match(text):
        raise ValueError(f"{field}要写成 YYYY-MM-DD")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field}不是合法日期") from exc
    return text


def assert_not_future(day: str | None, today: str | None = None, *, field: str = "烘焙日") -> None:
    if not day:
        return
    today = today or calendar_today()
    if day > today:
        raise ValueError(f"{field}不能晚于今天")


def window(roast: str | None) -> tuple[int, int, int]:
    """按豆卡 roast 文本命中窗口。包含匹配，浅先于中浅先于中深先于深先于中。"""
    text = roast or ""
    if "浅" in text:
        return WINDOW_LIGHT
    if "中浅" in text:
        return WINDOW_LIGHT
    if "中深" in text:
        return WINDOW_MEDIUM_DARK
    if "深" in text:
        return WINDOW_DARK
    if "中" in text:
        return WINDOW_MEDIUM
    return WINDOW_MEDIUM


def of(
    roasted_on: str | None,
    roast: str | None = None,
    opened_on: str | None = None,
    today: str | None = None,
) -> dict:
    today = today or calendar_today()
    opened_long = _opened_long(opened_on, today)
    roast_day = None
    if roasted_on:
        try:
            roast_day = parse_date(roasted_on)
        except ValueError:
            roast_day = None
    if not roast_day:
        return {
            "roasted_on": None,
            "days_after_roast": None,
            "phase": "unknown",
            "label": LABELS["unknown"],
            "opened_long": opened_long,
        }
    days = (date.fromisoformat(today) - date.fromisoformat(roast_day)).days
    rest_end, peak_end, stale_at = window(roast)
    if days < rest_end:
        phase = "resting"
    elif days < peak_end:
        phase = "peak"
    elif days < stale_at:
        phase = "fading"
    else:
        phase = "stale"
    return {
        "roasted_on": roast_day,
        "days_after_roast": days,
        "phase": phase,
        "label": LABELS[phase],
        "opened_long": opened_long,
    }


def _opened_long(opened_on: str | None, today: str) -> bool:
    if not opened_on:
        return False
    try:
        opened = parse_date(str(opened_on)[:10], field="开封日")
    except ValueError:
        return False
    if not opened:
        return False
    return (date.fromisoformat(today) - date.fromisoformat(opened)).days > OPENED_LONG_AFTER
