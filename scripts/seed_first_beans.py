"""把手上这几包真豆子录进去（一次性，重复跑会跳过已存在的）。

用法：服务跑起来后 `uv run python scripts/seed_first_beans.py [端口] [图片目录]`

先备上「谁喝的」常客：戚浩辰、丁瀚舟、孙琦（已有则跳过）。

几包的状态各不相同，正好把几条口径演一遍：
- 瑰夏村绿标036：227 g / 102 元，已经喝掉一些，现在称出 129.351 g
  → 走**盘点**。若走「开袋实称」会把单价分母从 227 改成 129.351，每克成本虚高 76%。
- 巴西南米纳斯：454 g / 119 元，还没开封 → 只入库，不开封、不称。
- MATYAZO CWS、晨曦焦糖：500 g / 380 元，还没开封 → 同上。

没给净含量的豆子也能录：不填 nominal_g 就只建豆卡，跟着「在库」出并标待入袋，
称过再入袋（见 store.list_beans）。
"""

from __future__ import annotations

import json
import mimetypes
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PORT = sys.argv[1] if len(sys.argv) > 1 else "8000"
PHOTO_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else None
BASE = f"http://127.0.0.1:{PORT}"

# 「谁喝的」芯片：人可以随时增删，这三个人是吧台常客，入库时先备上
DEFAULT_PEOPLE = ["戚浩辰", "丁瀚舟", "孙琦"]

GREEN, YELLOW, DIM, OFF = "\033[32m", "\033[33m", "\033[2m", "\033[0m"

BEANS = [
    {
        "bean": {
            "name": "瑰夏村 绿标036",
            "origin": "埃塞俄比亚 迪马 Dimma",
            "varietal": "伊鲁巴博森林 Illubabor Forest",
            "process": "水洗",
            "roast": "浅烘",
            "note": '61" coffee · 包装标 7°N 40°W',
            "tags": ["白花", "柑橘", "核果", "黄糖", "绿茶"],
            "nominal_g": 227,
            # 单价按 102/227 算，不按现在剩的 129.351 —— 这也是下面走盘点不走实称的原因
            "price": 102,
        },
        # 已经喝掉一些之后称的 → 盘点，不是开袋实称
        "opened": True,
        "stocktake_g": 129.351,
        "photo": "瑰夏村绿标036.jpg",
    },
    {
        "bean": {
            "name": "巴西 南米纳斯",
            "origin": "巴西 南米纳斯 Sul De Minas",
            "varietal": "黄波旁 Bourbon Amarelo",
            "process": "日晒",
            "roast": "中深烘",
            "note": '61" coffee · 包装标 15°S 47°W',
            "tags": ["花生", "焦糖", "可可", "奶油"],
            "nominal_g": 454,
            "price": 119,
        },
        "opened": False,
        "stocktake_g": None,
        "photo": "巴西南米纳斯.jpg",
    },
    {
        "bean": {
            "name": "MATYAZO CWS 黑莓可可",
            "origin": "卢旺达 恩戈罗雷罗 Ngororero District",
            "varietal": "红波旁 Red Bourbon",
            "producer": "Matyazo CWS 处理厂",
            "altitude": "1500-2200m",
            "process": "水洗",
            "roast": "中烘",
            "water_temp": 88,
            "note": "0566 Exquisite Coffee Boutique · 纸罐装",
            "tags": ["黑莓", "丁香", "阿克苏苹果", "太妃糖"],
            # 豆卡上店家给了整套参数，直接存成这支豆的默认
            "brew_method": "volcano",
            "brew_dose_g": 15,
            "brew_ratio": 14,
            "brew_note": 'KONO 法兰绒 · 富士 #7 · 水质 TDS 10-15（非常规 70）· 目标 2\'15"',
            "nominal_g": 500,
            "price": 380,
        },
        "opened": False,
        "stocktake_g": None,
        "photo": "matyazo-cws.jpg",
    },
    {
        # 四产区拼配。产国/产区/品种/处理法都是多个，字段本来就是文本，照豆卡原样存。
        "bean": {
            "name": "晨曦焦糖",
            "origin": "拼配 · 埃塞俄比亚 耶加雪菲 & 巴西 米纳斯吉拉斯 & "
                      "卢旺达 恩戈罗雷罗 & 洪都拉斯 弗朗西斯科-莫拉桑",
            "varietal": "原生种、黄波旁、波旁、卡图拉",
            "process": "水洗、日晒、厌氧日晒",
            "roast": "日系深烘",
            "note": "0566 Exquisite Coffee Boutique · 纸罐装 · "
                    "入口醇厚黑巧，中段焦糖太妃，尾端烤坚果，隐约朗姆酒香",
            "tags": ["巧克力", "烤榛子", "粽糖", "酒香"],
            # 这张豆卡只讲烘焙，没给粉水/水温/时长，冲煮就用系统默认
            "nominal_g": 500,
            "price": 380,
        },
        "opened": False,
        "stocktake_g": None,
        "photo": "chenxi-jiaotang.jpg",
    },
    {
        "bean": {
            "name": "马森秋 Masincho",
            "origin": "埃塞俄比亚 西达玛 Sidama",
            "varietal": "74158",
            "producer": "Yaye-Testi 处理站",
            "process": "水洗",
            "roast": "中浅烘",
            "water_temp": 93,
            "note": "言一社 · 单一产区 · 豆卡处理站亦作 Yaya-testi",
            "tags": ["覆盆子", "茉莉", "柑橘"],
            "brew_method": "v60",
            "brew_dose_g": 16,
            "brew_ratio": 15,
            "brew_note": "V60 16 g / 92–94°C / 240 g（1:15）。闷蒸 30 g 30 s；"
                         "1:00 注到 100 g；1:45 中心注到 240 g。"
                         "聪明杯 20 g / 90–93°C / 300 g；法压 15 g / 92°C / 225 g。",
            "nominal_g": 500,
            "price": 102,
        },
        "opened": True,
        "writeoff": True,
        "closed": True,
        "stocktake_g": None,
        "photo": None,
    },
    {
        "bean": {
            "name": "墨白",
            "origin": "哥伦比亚 蕙兰 Huila",
            "varietal": "铁皮卡 Typica",
            "process": "水洗",
            "roast": "深烘",
            "water_temp": 88,
            "note": "言一社 · 单一产区 SOE · 意式 / 手冲",
            "tags": ["太妃糖", "奶油坚果"],
            "brew_method": "v60",
            "brew_dose_g": 15,
            "brew_ratio": 15,
            "brew_note": "V60 15 g / 86–89°C / 225 g（1:15）。闷蒸 30 g 30 s；"
                         "约 1:00 注到 130 g；约 2:00 到 225 g。"
                         "聪明杯 20 g / 90°C / 300 g；法压 15 g / 92°C / 225 g；"
                         "意式 15–18 g / 91–93°C / 1.5–2 倍液重 / 9 bar / 25–30 s。",
            "nominal_g": 500,
            "price": 102,
        },
        "opened": True,
        "writeoff": True,
        "closed": True,
        "stocktake_g": None,
        "photo": None,
    },
]


def call(method: str, path: str, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Session": "seed", "X-Source": "web"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def upload(bean_id: int, path: Path, kind: str = "pack"):
    """手搓 multipart，省得为一个脚本引第三方库。"""
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="kind"\r\n\r\n{kind}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {ctype}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{BASE}/api/beans/{bean_id}/photos",
        method="POST",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-Session": "seed"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main() -> int:
    try:
        call("GET", "/api/health")
    except urllib.error.URLError:
        print(f"连不上 {BASE}，先把服务跑起来。")
        return 1

    _, roster = call("GET", "/api/people?include_inactive=true")
    have_people = {p["name"] for p in roster.get("people") or []}
    for name in DEFAULT_PEOPLE:
        if name in have_people:
            print(f"{DIM}谁喝的已有「{name}」{OFF}")
            continue
        call("POST", "/api/people", {"name": name})
        print(f"谁喝的备上 {name}")

    _, existing = call("GET", "/api/beans?scope=all")
    have = {b["name"] for b in existing["beans"]}

    for entry in BEANS:
        spec = entry["bean"]
        if spec["name"] in have:
            print(f"{DIM}已经有「{spec['name']}」了，跳过{OFF}")
            continue

        print(f"\n{YELLOW}{spec['name']}{OFF}")
        _, bean = call("POST", "/api/beans", spec)
        lot = bean["lots"][0] if bean["lots"] else None

        if lot is None:
            print(f"{DIM}   没给净含量，只建了豆卡；称过之后在豆卡里「入袋」{OFF}")
        else:
            print(f"   入库 {lot['nominal_g']:g} g（袋上印的）")

            if entry["opened"]:
                call("POST", f"/api/lots/{lot['id']}/open")
                print("   标记开封")

            if entry["stocktake_g"] is not None:
                _, out = call(
                    "POST",
                    f"/api/lots/{lot['id']}/adjust",
                    {"actual_g": entry["stocktake_g"], "note": "入库前已经喝掉一些，称了一次"},
                )
                print(f"   盘点到 {entry['stocktake_g']} g（差 {out['delta_g']:+.1f} g 记成校正）")

            if entry.get("writeoff"):
                _, out = call(
                    "POST",
                    f"/api/lots/{lot['id']}/writeoff",
                    {"note": "补录：已喝光，克重和钱进统计，不算到人"},
                )
                print(f"   整袋补录 {out.get('amount_g')} g（不算杯）")

            if entry.get("closed"):
                _, out = call(
                    "POST",
                    f"/api/lots/{lot['id']}/close",
                    {"note": "关袋（整袋消耗已另记）"},
                )
                print(f"   关袋进历史（结清 {out.get('deviation_g')} g）")

        if PHOTO_DIR and entry.get("photo"):
            img = PHOTO_DIR / entry["photo"]
            if img.exists():
                upload(bean["id"], img, "pack")
                print(f"   挂上包装图 {img.name}")
            else:
                print(f"{DIM}   没找到 {img}，跳过图{OFF}")
            # 店家豆卡（那张印参数的纸）单独存一类，缩略图不会选它
            card = img.with_name(f"{img.stem}-card{img.suffix}")
            if card.exists():
                upload(bean["id"], card, "card")
                print(f"   挂上豆卡 {card.name}")

        _, fresh = call("GET", f"/api/beans/{bean['id']}")
        if lot is None:
            print(f"   {GREEN}豆卡建好了，待入袋{OFF}")
        else:
            d = fresh["avg_dose"]
            cost = f" · 每克 {lot['price'] / lot['nominal_g']:.3f} 元" if lot.get("price") else ""
            print(
                f"   {GREEN}账面 {fresh['balance_g']:.1f} g · "
                f"约 {fresh['cups_left']} 杯（按平均 {d['avg_g']} g）{cost}{OFF}"
            )

    print(f"\n{GREEN}录完了。{OFF}打开 {BASE} 看豆库。\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
