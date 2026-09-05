"""对着真在跑的服务走一遍完整场景，把关键口径打出来看。

用法：拿一个**空库**起服务，再
    COFFEEBAR_DATA=/tmp/cb-smoke uv run uvicorn app.main:app --port 8011
    uv run python scripts/smoke.py 8011

只读 HTTP 接口，不碰数据库文件，但**会往库里写演示豆子和演示人**，而且有几条断言
数的是全库总量（花了多少钱、喝了多少杯），所以：
- 库里已经有豆子就直接拒跑，别把「哥伦比亚 蕙兰」这种演示数据混进真豆库；
- 真要往非空库里跑，加 --force，跑完自己收拾。
"""

from __future__ import annotations

import http.cookiejar
import json
import sys
import urllib.error
import urllib.request

args = [a for a in sys.argv[1:] if not a.startswith("-")]
FORCE = "--force" in sys.argv
PORT = args[0] if args else "8000"
BASE = f"http://127.0.0.1:{PORT}"

YELLOW, GREEN, RED, DIM, OFF = "\033[33m", "\033[32m", "\033[31m", "\033[2m", "\033[0m"
failures: list[str] = []
COOKIES = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIES))


def call(method: str, path: str, body=None, session="smoke", source="web"):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            "X-Session": session,
            "X-Source": source,
        },
    )
    try:
        with OPENER.open(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def step(n, title):
    print(f"\n{YELLOW}{n}. {title}{OFF}")


def ok(cond, msg):
    print(f"   {GREEN if cond else RED}{'✓' if cond else '✗'}{OFF} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    try:
        _, health = call("GET", "/api/health")
    except urllib.error.URLError:
        print(f"{RED}连不上 {BASE}。先把服务跑起来。{OFF}")
        return 1
    print(f"{DIM}服务在 {BASE} · 库 {health['db']}{OFF}")

    if health["beans"] and not FORCE:
        print(
            f"\n{RED}这个库里已经有 {health['beans']} 支豆子了，不往里写演示数据。{OFF}\n"
            f"{DIM}smoke 会建演示豆和演示人，还要数全库总量。换个空库：\n"
            f"  COFFEEBAR_DATA=/tmp/cb-smoke uv run uvicorn app.main:app --port 8011\n"
            f"真要往这个库里跑就加 --force。{OFF}"
        )
        return 1

    step(0, "注册一个演示账号")
    code, acc = call("POST", "/api/auth/register", {
        "email": "smoke@coffeebar.local", "password": "smokepass",
    })
    if code == 409:
        code, acc = call("POST", "/api/auth/login", {
            "email": "smoke@coffeebar.local", "password": "smokepass",
        })
    ok(code in (200, 201), f"登录 {acc.get('email') if isinstance(acc, dict) else acc}")

    step(1, "建一支豆，一袋 200 g / ¥128，刚拆袋不称重")
    _, bean = call("POST", "/api/beans", {
        "name": "耶加雪菲 果丁丁", "origin": "埃塞俄比亚", "process": "水洗",
        "roast": "浅烘", "water_temp": 92, "nominal_g": 200, "price": 128,
        "tags": ["水洗", "柑橘", "花香"],
    })
    bid, lot = bean["id"], bean["lots"][0]["id"]
    ok(bean["lots"][0]["measured_g"] is None, "实称留空，默认按包装标称扣")
    ok(bean["balance_g"] == 200, f"账面 {bean['balance_g']} g")

    step(2, "冲三次，每次粉量都不一样")
    for grams, who in [(16, "丁瀚舟"), (14.5, "戚浩辰"), (18, "丁瀚舟")]:
        _, r = call("POST", "/api/brews", {
            "lot_id": lot, "amount_g": grams, "person": who,
            "brew_method": "v60", "brew_ratio": 16,
        })
        print(f"   {who} 扣 {r['amount_g']} g · 这杯 ¥{r['cost']:.2f} · 剩 {r['balance_g']:.1f} g")
    _, bean = call("GET", f"/api/beans/{bid}")
    ok(abs(bean["balance_g"] - 151.5) < 0.01, f"账面按实际用量扣到 {bean['balance_g']} g")

    step(3, "平均每杯粉量从实际用量算，不是固定 15 g")
    a = bean["avg_dose"]
    print(f"   平均 {a['avg_g']} g（{a['lo_g']}–{a['hi_g']}）· 来源 {a['source']}")
    ok(a["avg_g"] == 16.2, "16 / 14.5 / 18 的平均是 16.2 g")
    ok(bean["cups_left"] == 9, f"还能冲约 {bean['cups_left']} 杯（151.5 ÷ 16.2）")

    step(4, "撤回最后一笔：克数加回去，行还在只是划掉")
    _, rows = call("GET", f"/api/consumption?bean_id={bid}&limit=1")
    cid = rows["rows"][0]["id"]
    call("POST", f"/api/consumption/{cid}/void", {"reason": "手滑记两遍"})
    _, bean = call("GET", f"/api/beans/{bid}")
    voided = [r for r in bean["log"] if r["voided_at"]]
    ok(abs(bean["balance_g"] - 169.5) < 0.01, f"账面回到 {bean['balance_g']} g")
    ok(len(bean["log"]) == 3 and len(voided) == 1, "三行流水都在，其中一行划掉")
    ok(bean["avg_dose"]["cups"] == 2, "平均粉量只算没撤回的两杯")

    step(5, "补开袋实称 194 g：账面跟着变，已发生的钱不回溯改写")
    _, rows = call("GET", f"/api/consumption?bean_id={bid}&limit=3")
    before = rows["rows"][-1]["unit_cost"]
    call("POST", f"/api/lots/{lot}/measure", {"measured_g": 194})
    _, rows = call("GET", f"/api/consumption?bean_id={bid}&limit=3")
    after = rows["rows"][-1]["unit_cost"]
    _, bean = call("GET", f"/api/beans/{bid}")
    ok(before == after, f"单价快照仍是 ¥{before:.4f}/g（分母从 200 变 194 也没改写）")
    ok(abs(bean["balance_g"] - 163.5) < 0.01, f"账面按新的可用克重变成 {bean['balance_g']} g")

    step(6, "冲煮方案按当场输入算，各段加总严格等于总水")
    _, p = call("GET", "/api/brew/plan?method=kasuya&dose_g=18&ratio=15")
    total = sum(s["add_g"] for s in p["stages"])
    print(f"   {p['method_label']} · 18 g · 1:15 → 总水 {p['total_water_g']} g")
    for s in p["stages"]:
        add = f"+{s['add_g']} g" if s["add_g"] else "停手"
        add_r = f"1:{s['add_ratio']:.2f}" if s["add_g"] else "—"
        print(
            f"     {s['name']:<6}{add:>7} {add_r:>7}  秤到 {s['target_g']:>3} g  "
            f"1:{s['target_ratio']:.2f}  {s['seconds']:>2}s  {s['how']}"
        )
    ok(total == p["total_water_g"], f"各段加总 {total} = 总水 {p['total_water_g']}")

    step(7, "统计出数字")
    _, s = call("GET", "/api/stats?period=all")
    print(f"   {s['beans_g']} g / {s['cups']} 杯 · 平均 {s['avg_dose']['avg_g']} g")
    print(f"   喝掉 ¥{s['spent']:.2f} · 买进 ¥{s['bought']:.0f} · 在库还值 ¥{s['on_hand']:.0f}")
    for row in s["by_person"]:
        print(f"     {row['name']}：{row['beans_g']} g / {row['cups']} 杯 / 平均 {row['avg_dose_g']} g / ¥{row['spent']:.2f}")
    ok(s["cups"] == 2, "撤回的那杯不进汇总")
    ok(s["spent"] < s["bought"], "喝掉的钱和买进来的钱分开算")

    step(8, "写锁：网页之间提示接管，MCP 硬拒绝")
    call("POST", f"/api/locks/bean:{bid}", {"holder": "小主机"}, session="host")
    code, body = call("POST", f"/api/locks/bean:{bid}", {"holder": "手机"}, session="phone")
    print(f"   手机来拿锁 → HTTP {code}：{body['message']}")
    ok(code == 423 and body["can_take_over"], "网页可接管")
    code, body = call("POST", f"/api/locks/bean:{bid}", {"take_over": True}, session="mcp", source="mcp")
    ok(code == 423 and not body["can_take_over"], "MCP 抢不走，只能等人放手")
    code, _ = call("POST", f"/api/locks/bean:{bid}", {"holder": "手机", "take_over": True}, session="phone")
    ok(code == 200, "手机点一下接管成功")
    code, body = call("PUT", f"/api/locks/bean:{bid}", session="host")
    ok(code == 409, f"小主机续锁被拒：{body['message']}")
    call("DELETE", f"/api/locks/bean:{bid}", session="phone")

    step(9, "盘点后关袋，进历史")
    call("POST", f"/api/lots/{lot}/adjust", {"actual_g": 6})
    _, r = call("POST", f"/api/lots/{lot}/close", {"note": "扫干净了"})
    ok(abs(r["lot"]["balance_g"]) < 0.01, f"关袋偏差 {r['deviation_g']:+} g 结清，账面归零")
    # 只认自己这支豆，别数总数——库里可能已经有真豆子了
    _, in_stock = call("GET", "/api/beans")
    _, history = call("GET", "/api/beans?scope=history")
    ok(
        bid not in [b["id"] for b in in_stock["beans"]]
        and bid in [b["id"] for b in history["beans"]],
        "所有袋关了就进历史，不和在库混排",
    )

    step(10, "补货清单")
    _, bean2 = call("POST", "/api/beans", {"name": "哥伦比亚 蕙兰", "roast": "中烘", "nominal_g": 200, "price": 98})
    call("POST", "/api/brews", {"lot_id": bean2["lots"][0]["id"], "amount_g": 16, "person": "丁瀚舟"})
    call("POST", f"/api/lots/{bean2['lots'][0]['id']}/adjust", {"actual_g": 9})
    _, rs = call("GET", "/api/restock")
    for it in rs["items"]:
        print(f"   {it['name']}：剩 {it['balance_g']} g · {' · '.join(it['reasons'])}")
    ok(any("不够一杯了" in it["reasons"] for it in rs["items"]), "剩 9 g 会提示补货")

    step(11, "删掉一个人：人没了，他喝掉的豆和花掉的钱留在总账里")
    _, before = call("GET", "/api/stats?period=all")
    _, people = call("GET", "/api/people")
    target = next(p for p in people["people"] if p["name"] == "戚浩辰")
    print(f"   删之前提示：{target['name']} 名下有 {target['cups']} 条记录")
    _, out = call("DELETE", f"/api/people/{target['id']}")
    _, after = call("GET", "/api/stats?period=all")
    ok(out["orphaned"] == 1, f"{out['name']} 已删除，{out['orphaned']} 条记录变成「没记」")
    ok(
        after["cups"] == before["cups"] and after["beans_g"] == before["beans_g"],
        f"总数没变：{after['beans_g']} g / {after['cups']} 杯",
    )
    ok("没记" in {r["name"] for r in after["by_person"]}, "那笔归到「没记」，不算在任何人头上")

    print()
    if failures:
        print(f"{RED}{len(failures)} 项没过：{OFF}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"{GREEN}全部跑通。{OFF}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
