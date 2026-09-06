"""HTTP 层：建豆、选袋冲一次、撤回、写锁软/硬两种行为。"""

import pytest


def new_bean(client, name="西达摩 水洗", nominal=200, price=128.0):
    r = client.post(
        "/api/beans",
        json={"name": name, "roast": "浅烘", "origin": "埃塞俄比亚",
              "nominal_g": nominal, "price": price, "tags": ["水洗", "柑橘"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_create_bean_with_first_lot(client):
    bean = new_bean(client)
    assert bean["balance_g"] == 200
    assert len(bean["lots"]) == 1
    assert bean["tags"] == ["柑橘", "水洗"]
    assert bean["lots"][0]["measured_g"] is None, "刚拆袋不称重"


def test_bean_needs_name(client):
    assert client.post("/api/beans", json={"name": "  "}).status_code == 409


def test_brew_flow_and_cups_left(client):
    bean = new_bean(client)
    lot = bean["lots"][0]["id"]

    for g in (16, 15, 17):
        r = client.post("/api/brews", json={"lot_id": lot, "amount_g": g, "person": "丁瀚舟"})
        assert r.status_code == 201, r.text

    detail = client.get(f"/api/beans/{bean['id']}").json()
    assert detail["balance_g"] == pytest.approx(152)
    assert detail["avg_dose"]["avg_g"] == pytest.approx(16.0)
    assert detail["avg_dose"]["source"] == "bean"
    assert detail["cups_left"] == 9              # 152 / 16
    assert len(detail["log"]) == 3


def test_brew_rejects_overdraw_with_message(client):
    bean = new_bean(client, nominal=20)
    r = client.post("/api/brews", json={"lot_id": bean["lots"][0]["id"], "amount_g": 25})
    assert r.status_code == 409
    assert "不够" in r.json()["message"]


def test_void_and_unvoid_via_api(client):
    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    brew = client.post("/api/brews", json={"lot_id": lot, "amount_g": 16}).json()

    assert client.post(f"/api/consumption/{brew['id']}/void", json={"reason": "记错了"}).status_code == 200
    assert client.get(f"/api/beans/{bean['id']}").json()["balance_g"] == pytest.approx(200)

    rows = client.get("/api/consumption").json()["rows"]
    assert len(rows) == 1 and rows[0]["voided_at"], "只划掉不删"

    assert client.post(f"/api/consumption/{brew['id']}/unvoid").status_code == 200
    assert client.get(f"/api/beans/{bean['id']}").json()["balance_g"] == pytest.approx(184)


def test_delete_voided_via_api(client):
    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    brew = client.post("/api/brews", json={"lot_id": lot, "amount_g": 16}).json()

    assert client.delete(f"/api/consumption/{brew['id']}").status_code == 409
    assert client.post(f"/api/consumption/{brew['id']}/void").status_code == 200
    assert client.delete(f"/api/consumption/{brew['id']}").status_code == 200
    assert client.get("/api/consumption").json()["rows"] == []
    assert client.get(f"/api/beans/{bean['id']}").json()["balance_g"] == pytest.approx(200)


def test_reassign_person_via_api(client):
    bean = new_bean(client)
    brew = client.post(
        "/api/brews", json={"lot_id": bean["lots"][0]["id"], "amount_g": 16, "person": "戚浩辰"}
    ).json()

    assert client.post(f"/api/consumption/{brew['id']}/person", json={"person": "孙琦"}).status_code == 200
    assert client.get("/api/consumption").json()["rows"][0]["person_name"] == "孙琦"


def test_people_manage(client):
    bean = new_bean(client)
    client.post("/api/brews", json={"lot_id": bean["lots"][0]["id"], "amount_g": 15, "person": "戚浩辰"})

    people = client.get("/api/people").json()["people"]
    pid = people[0]["id"]

    assert client.patch(f"/api/people/{pid}", json={"name": "王工"}).status_code == 200
    assert client.get("/api/people").json()["people"][0]["name"] == "王工"

    client.patch(f"/api/people/{pid}", json={"active": False})
    assert client.get("/api/people").json()["people"] == []
    assert len(client.get("/api/people?include_inactive=true").json()["people"]) == 1

    profile = client.get(f"/api/people/{pid}/profile").json()
    assert profile["cups"] == 1, "停用后画像还在"
    assert profile["enough_sample"] is False


def test_delete_person_via_api(client):
    """人能真删掉，但他喝掉的豆和花掉的钱留在总账里。"""
    bean = new_bean(client, nominal=500, price=250.0)
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 16, "person": "戚浩辰"})
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 15, "person": "丁瀚舟"})

    people = {p["name"]: p for p in client.get("/api/people").json()["people"]}
    assert people["戚浩辰"]["cups"] == 1, "列表要带条数，删之前得能提示影响面"

    r = client.delete(f"/api/people/{people['戚浩辰']['id']}")
    assert r.status_code == 200
    assert r.json()["orphaned"] == 1
    assert [p["name"] for p in r.json()["people"]] == ["丁瀚舟"]

    s = client.get("/api/stats", params={"period": "all"}).json()
    assert s["cups"] == 2 and s["beans_g"] == pytest.approx(31), "总数不受删人影响"
    assert {p["name"] for p in s["by_person"]} == {"丁瀚舟", "没记"}

    rows = client.get("/api/consumption").json()["rows"]
    assert len(rows) == 2
    assert any(r["person_name"] is None for r in rows), "那笔还在，只是没了归属"


def test_delete_missing_person_via_api(client):
    assert client.delete("/api/people/999").status_code == 409


def test_delete_bean_card(client):
    """建错的卡（比如 smoke 写进来的演示豆）要能整张删掉。"""
    from app import db

    bean = new_bean(client, name="演示豆")
    photo = client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("bag.png", _png(), "image/png")},
        data={"kind": "pack"},
    ).json()
    name = photo["path"].split("/")[-1]
    assert (db.PHOTO_DIR / name).exists()

    r = client.delete(f"/api/beans/{bean['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "演示豆"
    assert client.get(f"/api/beans/{bean['id']}").status_code == 404
    assert client.get("/api/beans?scope=all").json()["beans"] == []
    assert not (db.PHOTO_DIR / name).exists(), "照片文件跟着清掉"
    # 统计里那笔买入价也一起走
    assert client.get("/api/stats?period=all").json()["bought"] == 0


def test_delete_bean_refuses_live_brews(client):
    """有没撤回的消耗时，不带 mode 仍拒删，避免旧客户端一键抹账。"""
    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    brew = client.post("/api/brews", json={"lot_id": lot, "amount_g": 16}).json()

    r = client.delete(f"/api/beans/{bean['id']}")
    assert r.status_code == 409
    assert "花掉的钱" in r.json()["message"]
    assert client.get(f"/api/beans/{bean['id']}").status_code == 200

    # 撤回之后没有活记录，不带 mode 也能物理删
    client.post(f"/api/consumption/{brew['id']}/void", json={"reason": "记错了"})
    assert client.delete(f"/api/beans/{bean['id']}").status_code == 200


def test_delete_bean_keep_spend(client):
    """真喝过：从豆库收起，统计里杯数和钱还在。"""
    bean = new_bean(client, name="喝过的豆", price=128.0, nominal=200)
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 16})
    before = client.get("/api/stats", params={"period": "all"}).json()
    assert before["spent"] == pytest.approx(10.24)  # 16 × 128/200
    assert before["on_hand"] == pytest.approx(117.76)  # 184 × 0.64
    assert any(b["name"] == "喝过的豆" for b in before["by_bean"])

    r = client.delete(f"/api/beans/{bean['id']}", params={"mode": "keep"})
    assert r.status_code == 200, r.text
    assert r.json()["kept_spend"] is True
    assert client.get(f"/api/beans/{bean['id']}").status_code == 404
    assert client.get("/api/beans?scope=all").json()["beans"] == []

    after = client.get("/api/stats", params={"period": "all"}).json()
    assert after["spent"] == pytest.approx(before["spent"])
    assert after["bought"] == pytest.approx(before["bought"])
    assert after["on_hand"] == pytest.approx(0)
    assert any(b["name"] == "喝过的豆" for b in after["by_bean"])
    assert all(row["id"] != bean["id"] for row in client.get("/api/restock").json()["items"])


def test_delete_bean_wipe_clears_spend(client):
    """建错的测试卡：连流水一起抹，统计里那几笔钱也没了。"""
    bean = new_bean(client, name="抹掉的豆", price=128.0, nominal=200)
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 16})
    assert client.get("/api/stats", params={"period": "all"}).json()["spent"] > 0

    r = client.delete(f"/api/beans/{bean['id']}", params={"mode": "wipe"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/beans/{bean['id']}").status_code == 404
    after = client.get("/api/stats", params={"period": "all"}).json()
    assert after["spent"] == pytest.approx(0)
    assert after["bought"] == pytest.approx(0)
    assert after["by_bean"] == []


def test_delete_bean_keeps_others(client):
    keep = new_bean(client, name="留着的豆")
    gone = new_bean(client, name="删掉的豆")
    assert client.delete(f"/api/beans/{gone['id']}").status_code == 200
    names = [b["name"] for b in client.get("/api/beans?scope=all").json()["beans"]]
    assert names == ["留着的豆"]
    assert client.get(f"/api/beans/{keep['id']}").status_code == 200


def test_delete_bean_of_other_account(client):
    bean = new_bean(client, name="A 的豆")
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "nosy@coffeebar.local", "password": "testpass1"},
    )
    assert client.delete(f"/api/beans/{bean['id']}").status_code == 404


def test_map_pins_from_origin(client):
    new_bean(client, name="西达玛豆")
    blend = client.post(
        "/api/beans",
        json={
            "name": "晨曦焦糖",
            "origin": "拼配 · 埃塞俄比亚 耶加雪菲 & 巴西 米纳斯吉拉斯 & "
            "卢旺达 恩戈罗雷罗 & 洪都拉斯 弗朗西斯科-莫拉桑",
        },
    ).json()
    mystery = client.post("/api/beans", json={"name": "虚构日晒", "origin": "【测试】无此地"}).json()
    data = client.get("/api/map").json()
    labels = {p["label"] for p in data["pins"] if p["bean_id"] == blend["id"]}
    assert "耶加雪菲" in "".join(labels) or any("耶加雪菲" in (p["label"] or "") for p in data["pins"])
    assert sum(1 for p in data["pins"] if p["bean_id"] == blend["id"]) == 4
    assert any(u["id"] == mystery["id"] for u in data["unplaced"])
    sidama = [p for p in data["pins"] if p["name"] == "西达玛豆"]
    assert sidama and sidama[0]["source"] == "gazetteer"
    assert sidama[0]["balance_g"] == 200
    assert sidama[0]["roast"] == "浅烘"
    assert "柑橘" in sidama[0]["tags"]
    assert sidama[0]["origin"] == "埃塞俄比亚"
    eth = next(o for o in data["origins"] if o["key"] == "ethiopia")
    assert eth["kind"] == "country"
    assert eth["iso"] == "231"
    assert eth["altitude"] and eth["beans"] and eth["flavors"] and eth["famous"]
    assert any(o["key"] == "yirgacheffe" and o["kind"] == "region" for o in data["origins"])


def test_map_click_not_overwritten_and_hidden_when_deleted(client):
    bean = new_bean(client, name="要手点")
    r = client.put(
        f"/api/beans/{bean['id']}/places",
        json={"places": [{"lat": 35.6, "lng": 139.7, "label": "东京"}]},
    )
    assert r.status_code == 200, r.text
    client.patch(f"/api/beans/{bean['id']}", json={"origin": "哥伦比亚 蕙兰 Huila"})
    pins = client.get("/api/map").json()["pins"]
    mine = [p for p in pins if p["bean_id"] == bean["id"]]
    assert len(mine) == 1
    assert mine[0]["source"] == "click"
    assert mine[0]["lat"] == pytest.approx(35.6)

    client.post(f"/api/beans/{bean['id']}/places/guess")
    guessed = [p for p in client.get("/api/map").json()["pins"] if p["bean_id"] == bean["id"]]
    assert guessed[0]["source"] == "gazetteer"
    assert "蕙兰" in (guessed[0]["label"] or "")

    client.delete(f"/api/beans/{bean['id']}")
    left = client.get("/api/map").json()
    assert all(p["bean_id"] != bean["id"] for p in left["pins"])
    assert all(u["id"] != bean["id"] for u in left["unplaced"])


def test_map_of_other_account(client):
    bean = new_bean(client, name="A 的产地豆")
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "mapnosy@coffeebar.local", "password": "testpass1"},
    )
    assert client.get("/api/map").json()["pins"] == []
    assert client.put(
        f"/api/beans/{bean['id']}/places",
        json={"places": [{"lat": 1, "lng": 2}]},
    ).status_code == 404


def test_delete_bean_blocked_by_other_session(client):
    bean = new_bean(client)
    client.post(
        f"/api/locks/bean:{bean['id']}",
        json={"holder": "另一台"},
        headers={"X-Session": "other"},
    )
    r = client.delete(f"/api/beans/{bean['id']}", headers={"X-Session": "mine"})
    assert r.status_code == 423


def _png():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (120, 80, 50)).save(buf, "PNG")
    return buf.getvalue()


def test_add_second_lot_not_new_bean(client):
    bean = new_bean(client, price=118.0)
    r = client.post(f"/api/beans/{bean['id']}/lots", json={"nominal_g": 200, "price": 128.0})
    assert r.status_code == 201

    detail = client.get(f"/api/beans/{bean['id']}").json()
    assert len(detail["lots"]) == 2
    assert detail["balance_g"] == pytest.approx(400)
    assert len(client.get("/api/beans").json()["beans"]) == 1, "同支豆不该出现两张卡"


def test_measure_then_snapshot_unchanged(client):
    bean = new_bean(client, nominal=200, price=128.0)
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 16})

    client.post(f"/api/lots/{lot}/measure", json={"measured_g": 150})

    row = client.get("/api/consumption").json()["rows"][0]
    assert row["unit_cost"] == pytest.approx(128 / 200), "已发生的钱不回溯改写"


def test_close_lot_reports_deviation(client):
    bean = new_bean(client, nominal=200)
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 190})

    r = client.post(f"/api/lots/{lot}/close", json={"note": "扫不干净"})
    assert r.json()["deviation_g"] == pytest.approx(10)

    beans = client.get("/api/beans").json()["beans"]
    assert beans == [], "所有袋关了就进历史，默认不和在库混排"
    assert len(client.get("/api/beans?scope=history").json()["beans"]) == 1


def test_brew_plan_endpoint(client):
    p = client.get("/api/brew/plan", params={"method": "kasuya", "dose_g": 18, "ratio": 15}).json()
    assert p["total_water_g"] == 270
    assert sum(s["add_g"] for s in p["stages"]) == 270


def test_stats_endpoint(client):
    bean = new_bean(client, nominal=500, price=250.0)
    lot = bean["lots"][0]["id"]
    for g, who in [(16, "丁瀚舟"), (14, "戚浩辰"), (18, "丁瀚舟")]:
        client.post("/api/brews", json={"lot_id": lot, "amount_g": g, "person": who})

    s = client.get("/api/stats", params={"period": "all"}).json()
    assert s["cups"] == 3
    assert s["beans_g"] == pytest.approx(48)
    assert s["avg_dose"]["avg_g"] == pytest.approx(16.0)
    assert s["spent"] == pytest.approx(48 * 250 / 500)
    assert s["bought"] == pytest.approx(250.0)
    assert [p["name"] for p in s["by_person"]] == ["丁瀚舟", "戚浩辰"]
    assert s["by_person"][0]["beans_g"] == pytest.approx(34)


def test_restock_endpoint(client):
    bean = new_bean(client, nominal=200)
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 16})
    client.post(f"/api/lots/{lot}/adjust", json={"actual_g": 8})

    data = client.get("/api/restock").json()
    items = data["items"]
    assert len(items) == 1
    assert items[0]["cups_left"] == 0
    assert data["spirits"] == []


# ── 写锁 ────────────────────────────────────────────────────


def test_web_can_take_over_lock(client):
    """网页之间是软锁：提示接管，不用干等超时。"""
    bean = new_bean(client)
    res = f"bean:{bean['id']}"

    assert client.post(f"/api/locks/{res}", json={"holder": "小主机"},
                       headers={"X-Session": "s1"}).status_code == 200

    r = client.post(f"/api/locks/{res}", json={"holder": "手机"}, headers={"X-Session": "s2"})
    assert r.status_code == 423
    body = r.json()
    assert body["can_take_over"] is True
    assert "要接管吗" in body["message"]

    r = client.post(f"/api/locks/{res}", json={"holder": "手机", "take_over": True},
                    headers={"X-Session": "s2"})
    assert r.status_code == 200, "点一下就能接管"

    r = client.put(f"/api/locks/{res}", headers={"X-Session": "s1"})
    assert r.status_code == 409
    assert "接管" in r.json()["message"], "旧会话要被明确告知没保存"


def test_mcp_source_is_hard_rejected(client):
    """非网页来源硬拒绝：Agent 不该替人抢锁。"""
    bean = new_bean(client)
    res = f"bean:{bean['id']}"
    client.post(f"/api/locks/{res}", json={"holder": "小主机"}, headers={"X-Session": "web1"})

    r = client.post(f"/api/locks/{res}", json={"holder": "Cursor", "take_over": True},
                    headers={"X-Session": "mcp1", "X-Source": "mcp"})
    assert r.status_code == 423
    assert r.json()["can_take_over"] is False

    r = client.post("/api/brews",
                    json={"lot_id": bean["lots"][0]["id"], "amount_g": 15},
                    headers={"X-Session": "mcp1", "X-Source": "mcp"})
    assert r.status_code == 423, "MCP 写入被拦下"


def test_lock_holder_can_write(client):
    bean = new_bean(client)
    res = f"bean:{bean['id']}"
    client.post(f"/api/locks/{res}", headers={"X-Session": "s1"})

    r = client.post("/api/brews", json={"lot_id": bean["lots"][0]["id"], "amount_g": 15},
                    headers={"X-Session": "s1"})
    assert r.status_code == 201

    client.delete(f"/api/locks/{res}", headers={"X-Session": "s1"})
    r = client.post("/api/brews", json={"lot_id": bean["lots"][0]["id"], "amount_g": 15},
                    headers={"X-Session": "other"})
    assert r.status_code == 201, "释放后谁都能写"


def test_reading_never_locked(client):
    """看统计、看豆卡不占锁。"""
    bean = new_bean(client)
    client.post(f"/api/locks/bean:{bean['id']}", headers={"X-Session": "s1"})

    assert client.get(f"/api/beans/{bean['id']}").status_code == 200
    assert client.get("/api/stats").status_code == 200
    assert client.get("/api/restock").status_code == 200
