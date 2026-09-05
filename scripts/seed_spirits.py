"""录入手上的基酒（一次性，重复跑会跳过已存在的）。

用法：服务跑起来后 `uv run python scripts/seed_spirits.py [端口] [图片目录]`
"""

from __future__ import annotations

import http.cookiejar
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

GREEN, YELLOW, DIM, OFF = "\033[32m", "\033[33m", "\033[2m", "\033[0m"

SPIRITS = [
    {
        "spirit": {
            "name": "格兰杰 谜 16年",
            "kind": "威士忌",
            "category": "单一麦芽",
            "origin": "苏格兰高地",
            "abv": 43,
            "flavor": "柑橘甜、圆润、一丝烟熏",
            "note": "Glenmorangie The Tribute · Traveller's Exclusive · "
                    "Heritage Spirit Batch · 全波本桶陈年 · 1L",
            "tags": ["柑橘", "波本桶", "高地", "旅行零售"],
            "nominal_ml": 1000,
            "price": 399,
        },
        "photo": "glenmorangie-tribute.jpg",
    },
]


COOKIES = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIES))


def ensure_login():
    code, _ = call("POST", "/api/auth/login", {
        "email": "local@coffeebar.local", "password": "coffeebar-local",
    })
    if code == 200:
        return
    call("POST", "/api/auth/register", {
        "email": "local@coffeebar.local", "password": "coffeebar-local",
    })


def call(method: str, path: str, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Session": "seed", "X-Source": "web"},
    )
    try:
        with OPENER.open(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def upload(bottle_id: int, path: Path, kind: str = "pack"):
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
        f"{BASE}/api/spirits/{bottle_id}/photos",
        method="POST",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-Session": "seed"},
    )
    with OPENER.open(req) as r:
        return json.loads(r.read())


def main() -> int:
    try:
        call("GET", "/api/health")
    except urllib.error.URLError:
        print(f"连不上 {BASE}，先把服务跑起来。")
        return 1

    ensure_login()
    _, existing = call("GET", "/api/spirits?scope=all")
    have = {s["name"] for s in existing["spirits"]}

    for entry in SPIRITS:
        spec = entry["spirit"]
        if spec["name"] in have:
            print(f"{DIM}已经有「{spec['name']}」了，跳过{OFF}")
            continue

        print(f"\n{YELLOW}{spec['name']}{OFF}")
        _, bottle = call("POST", "/api/spirits", spec)
        lot = bottle["lots"][0]
        print(f"   入库 {lot['nominal_ml']:g} ml · {lot['price']:g} 元 · {lot['unit_cost']:.3f} 元/ml")

        if PHOTO_DIR:
            img = PHOTO_DIR / entry["photo"]
            if img.exists():
                upload(bottle["id"], img, "pack")
                print(f"   挂上瓶盒图 {img.name}")

        print(f"   {GREEN}账面 {bottle['balance_ml']:.0f} ml · {bottle['abv']:g}% vol{OFF}")

    print(f"\n{GREEN}录完了。{OFF}打开 {BASE} 看酒水。\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
