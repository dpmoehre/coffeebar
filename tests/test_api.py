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
        r = client.post("/api/brews", json={"lot_id": lot, "amount_g": g, "person": "我"})
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


def test_reassign_person_via_api(client):
    bean = new_bean(client)
    brew = client.post(
        "/api/brews", json={"lot_id": bean["lots"][0]["id"], "amount_g": 16, "person": "小王"}
    ).json()

    assert client.post(f"/api/consumption/{brew['id']}/person", json={"person": "阿陈"}).status_code == 200
    assert client.get("/api/consumption").json()["rows"][0]["person_name"] == "阿陈"


def test_people_manage(client):
    bean = new_bean(client)
    client.post("/api/brews", json={"lot_id": bean["lots"][0]["id"], "amount_g": 15, "person": "小王"})

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
    for g, who in [(16, "我"), (14, "小王"), (18, "我")]:
        client.post("/api/brews", json={"lot_id": lot, "amount_g": g, "person": who})

    s = client.get("/api/stats", params={"period": "all"}).json()
    assert s["cups"] == 3
    assert s["beans_g"] == pytest.approx(48)
    assert s["avg_dose"]["avg_g"] == pytest.approx(16.0)
    assert s["spent"] == pytest.approx(48 * 250 / 500)
    assert s["bought"] == pytest.approx(250.0)
    assert [p["name"] for p in s["by_person"]] == ["我", "小王"]
    assert s["by_person"][0]["beans_g"] == pytest.approx(34)


def test_restock_endpoint(client):
    bean = new_bean(client, nominal=200)
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 16})
    client.post(f"/api/lots/{lot}/adjust", json={"actual_g": 8})

    items = client.get("/api/restock").json()["items"]
    assert len(items) == 1
    assert items[0]["cups_left"] == 0


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
