"""画像上的喝法，不按「最常喝哪一支豆」。

一包两包就喝完，豆名说明不了口味。这里看烘焙、产地、豆种、冲煮、粉量、过冰，
再判断算不算老手，并推荐他还没喝过的处理法和产地。
"""

from __future__ import annotations

import sqlite3

from . import brew

# 教学用的下一袋。故意不限于库里已经有的豆子和处理法。
# seen 里出现任一词就跳过，避免把已经在喝的再推荐一遍。
BUY_CATALOG = [
    {
        "title": "哥斯达黎加 黄蜜",
        "origin": "哥斯达黎加 塔拉珠",
        "varietal": "卡杜拉、卡杜艾",
        "process": "黄蜜",
        "why": "果胶留在豆上晒到偏黄。甜比水洗厚，酸比日晒干净，没有厌氧那种酒感。",
        "seen": ("黄蜜", "蜜处理"),
    },
    {
        "title": "巴拿马 冷泉瑰夏",
        "origin": "巴拿马 博奎特",
        "varietal": "瑰夏",
        "process": "冷泉",
        "why": "冷水长时间浸出，花香和茶感比热发酵更干净。酸还在，少了日晒的发酵味。",
        "seen": ("冷泉", "冷发酵"),
    },
    {
        "title": "埃塞俄比亚 暗房日晒",
        "origin": "埃塞俄比亚 古吉",
        "varietal": "原生种",
        "process": "暗房日晒",
        "why": "不见光的慢干把热带水果和酒香收深。比普通日晒更沉，适合从清亮酸往厚水果走。",
        "seen": ("暗房",),
    },
    {
        "title": "肯尼亚 SL28 水洗",
        "origin": "肯尼亚 涅里",
        "varietal": "SL28",
        "process": "水洗",
        "why": "黑加仑、番茄枝那种磷酸感，和葡萄、草莓、柑橘不是同一条酸。",
        "seen": ("肯尼亚", "SL28", "SL34"),
    },
    {
        "title": "苏门答腊 湿刨",
        "origin": "印度尼西亚 苏门答腊",
        "varietal": "铁皮卡、卡帝姆",
        "process": "湿刨",
        "why": "泥土、香草、厚重，几乎没有花香。用来离开水果和茶感，知道咖啡还可以是这样。",
        "seen": ("湿刨", "苏门答腊", "曼特宁"),
    },
    {
        "title": "哥伦比亚 酒桶发酵",
        "origin": "哥伦比亚 慧兰",
        "varietal": "卡斯蒂略",
        "process": "酒桶发酵",
        "why": "豆子在酒桶里再发酵一轮，香料和酒香盖过花香。比厌氧日晒更靠桶，而不是靠缺氧。",
        "seen": ("酒桶",),
    },
]


def for_cups(rows: list) -> dict:
    """rows 是这个人的杯：amount_g, brew_method, note, roast, origin, varietal, process。"""
    cups = len(rows)
    roast = _top(rows, "roast")
    origin = _top(rows, "origin", shorten=_place)
    varietal = _top(rows, "varietal", shorten=_cjk_head)
    method_key = _top(rows, "brew_method")
    method_label = brew.METHODS.get(method_key["label"], method_key["label"]) if method_key["label"] else None
    dose_vals = [float(r["amount_g"]) for r in rows if r["amount_g"]]
    avg_dose = round(sum(dose_vals) / len(dose_vals), 1) if dose_vals else None
    ice = _ice(rows)
    processes = _distinct(rows, "process")
    origins = _distinct(rows, "origin", shorten=_place)
    veteran = _veteran(cups, rows, processes, origins)
    buys = _buys(rows, limit=3)
    return {
        "roast": roast,
        "origin": origin,
        "varietal": varietal,
        "brew_method": {"label": method_label, "cups": method_key["cups"], "of": cups} if method_label else None,
        "avg_dose_g": avg_dose,
        "ice": ice,
        "veteran": veteran,
        "buy": buys,
        "sentence": _sentence(roast, origin, varietal, method_label, avg_dose, ice, veteran),
    }


def _top(rows, key, shorten=None) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        raw = row[key] if not isinstance(row, dict) else row.get(key)
        label = shorten(raw) if shorten else (raw or "").strip()
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return {"label": None, "cups": 0, "of": len(rows)}
    label = max(counts, key=lambda k: (counts[k], k))
    return {"label": label, "cups": counts[label], "of": len(rows)}


def _distinct(rows, key, shorten=None) -> set[str]:
    out = set()
    for row in rows:
        raw = row[key] if not isinstance(row, dict) else row.get(key)
        label = shorten(raw) if shorten else ((raw or "").strip())
        if label:
            out.add(label)
    return out


def _place(origin: str | None) -> str | None:
    if not origin:
        return None
    kept = []
    for part in origin.replace("·", " ").split():
        if any("\u4e00" <= ch <= "\u9fff" for ch in part):
            kept.append(part)
        elif kept:
            break
    return " ".join(kept[:2]) if kept else origin.strip()


def _cjk_head(text: str | None) -> str | None:
    if not text:
        return None
    head = []
    for ch in text.strip():
        if "\u4e00" <= ch <= "\u9fff":
            head.append(ch)
        elif head:
            break
    return "".join(head) or text.strip()


def _ice_flag(note: str):
    if "不过冰" in note:
        return False
    if any(w in note for w in ("过冰", "冰杯", "加冰")):
        return True
    return None


def _ice(rows) -> dict:
    flags = []
    for row in rows:
        note = (row["note"] if not isinstance(row, dict) else row.get("note")) or ""
        flag = _ice_flag(note)
        if flag is not None:
            flags.append(flag)
    iced = sum(1 for f in flags if f)
    hot = sum(1 for f in flags if not f)
    recent = flags[-3:]
    recent_hot = sum(1 for f in recent if not f)
    recent_iced = sum(1 for f in recent if f)
    if iced == 0 and hot == 0:
        line = "备注里还没写过冰不过冰。"
    elif hot == 0:
        line = "会把咖啡放进冰里喝。"
    elif iced == 0:
        line = "记下的杯都是不过冰。"
    elif recent_hot > recent_iced and iced >= hot:
        line = f"过冰 {iced} 杯，不过冰 {hot} 杯。最近几杯改成不过冰。"
    elif hot >= iced:
        line = f"过冰 {iced} 杯，不过冰 {hot} 杯，热着喝更多。"
    else:
        line = f"过冰 {iced} 杯，不过冰 {hot} 杯，过冰更多。"
    return {"iced": iced, "hot": hot, "line": line}


def _veteran(cups: int, rows, processes: set[str], origins: set[str]) -> dict:
    notes = " ".join(
        ((r["note"] if not isinstance(r, dict) else r.get("note")) or "") for r in rows
    )
    technical = any(w in notes for w in ("1:", "节流", "截流", "截留", "°C", "℃"))
    if cups >= 8 and len(processes) >= 2 and len(origins) >= 2 and technical:
        return {
            "level": "老手",
            "line": "会自己改水温和粉水比，产地和处理法也不只一种，算喝咖啡的老手。",
        }
    if cups >= 3:
        return {
            "level": "在长",
            "line": "已经能分出杯子之间的差别，口味还集中在少数几种上。",
        }
    return {"level": "样本少", "line": "杯数还少，先不判断是不是老手。"}


def _buys(rows, limit: int = 3) -> list[dict]:
    blob = " ".join(
        " ".join(
            str((r[k] if not isinstance(r, dict) else r.get(k)) or "")
            for k in ("origin", "varietal", "process", "note")
        )
        for r in rows
    )
    out = []
    for item in BUY_CATALOG:
        if any(word in blob for word in item["seen"]):
            continue
        out.append(
            {
                "title": item["title"],
                "origin": item["origin"],
                "varietal": item["varietal"],
                "process": item["process"],
                "why": item["why"],
            }
        )
        if len(out) >= limit:
            break
    return out


def _sentence(roast, origin, varietal, method, dose, ice, veteran) -> str:
    bits = []
    if roast["label"]:
        bits.append(f"最爱{roast['label']}")
    if origin["label"]:
        bits.append(f"产地偏{origin['label']}")
    if varietal["label"]:
        bits.append(f"豆种偏{varietal['label']}")
    if method:
        bits.append(f"习惯 {method}")
    if dose is not None:
        bits.append(f"一杯大约 {dose} g 粉")
    head = "，".join(bits)
    tail = ice["line"] + veteran["line"]
    if head:
        return head + "。" + tail
    return tail
