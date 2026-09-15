"""挂耳按包扣，不走进手冲豆的克重剩余。"""


def _drip(client, name="【测试】挂耳", packs=3, nominal_g=8, price=24, **extra):
    r = client.post(
        "/api/beans",
        json={
            "name": name,
            "form": "dripbag",
            "packs": packs,
            "nominal_g": nominal_g,
            "price": price,
            "process": "挂耳",
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_dripbag_stays_out_of_bean_list(client):
    make_bean_via = client.post("/api/beans", json={"name": "【测试】手冲豆", "nominal_g": 200}).json()
    drip = _drip(client)
    beans = client.get("/api/beans?scope=stock").json()["beans"]
    names = [b["name"] for b in beans]
    assert make_bean_via["name"] in names
    assert drip["name"] not in names
    bags = client.get("/api/beans?scope=stock&form=dripbag").json()["beans"]
    assert [b["name"] for b in bags] == [drip["name"]]
    assert bags[0]["remaining_packs"] == 3
    assert bags[0]["cups_left"] == 3
    assert bags[0]["form"] == "dripbag"
    assert bags[0]["pack_cost"] == 8


def test_dripbag_consume_one_pack(client):
    drip = _drip(client, packs=2, price=16)
    lot_id = drip["lots"][0]["id"]
    assert drip["remaining_packs"] == 2
    first = client.post("/api/brews", json={"lot_id": lot_id, "person": "戚浩辰"}).json()
    assert first["amount_g"] == 8
    assert first["remaining_packs"] == 1
    assert first["filter_sheets"] is None
    assert first["cost"] == 8
    card = client.get(f"/api/beans/{drip['id']}").json()
    assert card["remaining_packs"] == 1
    assert card["cups_left"] == 1
    second = client.post("/api/brews", json={"lot_id": lot_id}).json()
    assert second["remaining_packs"] == 0
    assert second["near_empty"] is True
    empty = client.post("/api/brews", json={"lot_id": lot_id})
    assert empty.status_code == 409
    assert "没有剩的挂耳" in empty.json()["message"]


def test_dripbag_void_returns_pack(client):
    drip = _drip(client, packs=1)
    lot_id = drip["lots"][0]["id"]
    brew = client.post("/api/brews", json={"lot_id": lot_id}).json()
    client.post(f"/api/consumption/{brew['id']}/void", json={"reason": "记错了"})
    card = client.get(f"/api/beans/{drip['id']}").json()
    assert card["remaining_packs"] == 1


def test_dripbag_no_measure(client):
    drip = _drip(client)
    lot_id = drip["lots"][0]["id"]
    r = client.post(f"/api/lots/{lot_id}/measure", json={"measured_g": 8})
    assert r.status_code == 409
    assert "按包计" in r.json()["message"]


def test_dripbag_list_does_not_use_gram_average(client):
    _drip(client, packs=5, nominal_g=8)
    bags = client.get("/api/beans?form=dripbag").json()["beans"]
    assert bags[0]["avg_dose"]["source"] == "pack"
    assert bags[0]["near_empty"] is False


def test_dripbag_writeoff_rejected(client):
    drip = _drip(client, packs=2)
    r = client.post(f"/api/lots/{drip['lots'][0]['id']}/writeoff")
    assert r.status_code == 409
    assert "按包计" in r.json()["message"]


def test_dripbag_empty_goes_to_restock(client):
    drip = _drip(client, packs=1, name="【测试】见底挂耳")
    client.post("/api/brews", json={"lot_id": drip["lots"][0]["id"]})
    items = client.get("/api/restock").json()["items"]
    hit = next(it for it in items if it["id"] == drip["id"])
    assert "挂耳没有了" in hit["reasons"]
    assert hit["form"] == "dripbag"
    assert hit["cups_left"] == 0


def test_dripbag_does_not_pull_global_dose(client):
    drip = _drip(client, packs=2, nominal_g=8)
    client.post("/api/brews", json={"lot_id": drip["lots"][0]["id"]})
    listed = client.get("/api/beans").json()
    assert listed["avg_dose"]["source"] == "fallback"
    assert listed["avg_dose"]["avg_g"] == 15


def test_dripbag_needs_packs_to_stock(client):
    card = client.post(
        "/api/beans",
        json={"name": "【测试】待入挂耳", "form": "dripbag"},
    ).json()
    assert card["pending"] is True
    assert card["remaining_packs"] == 0
    bad = client.post(f"/api/beans/{card['id']}/lots", json={"nominal_g": 8})
    assert bad.status_code == 409
    assert "多少包" in bad.json()["message"]
