"""滤纸耗材：新开一包才计张，冲一杯扣一张，纸钱冻进该笔消耗。"""

import pytest

from tests.test_api import new_bean


def _paper(client, **extra):
    payload = {"name": "【测试】滤纸", "kind": "filter", **extra}
    r = client.post("/api/gear", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_no_pack_means_no_paper_money_and_no_restock(client):
    paper = _paper(client)
    assert paper["counting"] is False
    assert paper["sheets_left"] == 0
    assert client.get("/api/brew/methods").json()["filter"] is None
    assert client.get("/api/restock").json()["filters"] == []

    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    brew = client.post(
        "/api/brews",
        json={"lot_id": lot, "amount_g": 16, "brew_method": "v60"},
    ).json()
    assert brew["filter_cost"] is None
    assert brew["filter_sheets"] is None
    assert brew["cost"] == pytest.approx(16 * 128 / 200)
    assert client.get(f"/api/gear/{paper['id']}").json()["sheets_left"] == 0


def test_open_pack_then_brew_adds_paper_and_freezes_cost(client):
    paper = _paper(client)
    packed = client.post(
        f"/api/gear/{paper['id']}/packs",
        json={"sheets": 10, "price": 10},
    ).json()
    assert packed["kind"] == "filter"
    assert packed["counting"] is True
    assert packed["sheets_left"] == 10
    assert packed["open_pack"]["unit_cost"] == pytest.approx(1)

    teaser = client.get("/api/brew/methods").json()["filter"]
    assert teaser["remaining"] == 10
    assert teaser["unit_cost"] == pytest.approx(1)
    assert teaser["need_pick"] is False

    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    brew = client.post(
        "/api/brews",
        json={"lot_id": lot, "amount_g": 16, "brew_method": "v60"},
    ).json()
    assert brew["filter_sheets"] == 1
    assert brew["filter_cost"] == pytest.approx(1)
    assert brew["bean_cost"] == pytest.approx(16 * 128 / 200)
    assert brew["cost"] == pytest.approx(16 * 128 / 200 + 1)

    after = client.get(f"/api/gear/{paper['id']}").json()
    assert after["sheets_left"] == 9

    log = client.get(f"/api/beans/{bean['id']}").json()["log"][0]
    assert log["filter_sheets"] == 1
    assert log["filter_cost"] == pytest.approx(1)
    assert log["cost"] == pytest.approx(16 * 128 / 200 + 1)

    spent = client.get("/api/stats", params={"period": "all"}).json()["spent"]
    assert spent == pytest.approx(16 * 128 / 200 + 1)


def test_void_restores_sheet_and_unvoid_takes_it_again(client):
    paper = _paper(client)
    client.post(f"/api/gear/{paper['id']}/packs", json={"sheets": 5, "price": 5})
    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    brew = client.post("/api/brews", json={"lot_id": lot, "amount_g": 16, "brew_method": "v60"}).json()
    assert client.get(f"/api/gear/{paper['id']}").json()["sheets_left"] == 4

    assert client.post(f"/api/consumption/{brew['id']}/void").status_code == 200
    assert client.get(f"/api/gear/{paper['id']}").json()["sheets_left"] == 5
    spent = client.get("/api/stats", params={"period": "all"}).json()["spent"]
    assert spent == pytest.approx(0)

    assert client.post(f"/api/consumption/{brew['id']}/unvoid").status_code == 200
    assert client.get(f"/api/gear/{paper['id']}").json()["sheets_left"] == 4
    spent = client.get("/api/stats", params={"period": "all"}).json()["spent"]
    assert spent == pytest.approx(16 * 128 / 200 + 1)


def test_writeoff_does_not_use_paper(client):
    paper = _paper(client)
    client.post(f"/api/gear/{paper['id']}/packs", json={"sheets": 10, "price": 10})
    bean = new_bean(client, nominal=20, price=20)
    lot = bean["lots"][0]["id"]
    r = client.post(f"/api/lots/{lot}/writeoff")
    assert r.status_code == 201, r.text
    assert r.json()["as_cup"] == 0
    assert client.get(f"/api/gear/{paper['id']}").json()["sheets_left"] == 10


def test_as_cup_zero_skips_paper(client):
    paper = _paper(client)
    client.post(f"/api/gear/{paper['id']}/packs", json={"sheets": 10, "price": 10})
    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    brew = client.post(
        "/api/brews",
        json={"lot_id": lot, "amount_g": 16, "as_cup": 0},
    ).json()
    assert brew["as_cup"] == 0
    assert brew["filter_cost"] is None
    assert client.get(f"/api/gear/{paper['id']}").json()["sheets_left"] == 10


def test_other_open_pack_becomes_filter(client):
    other = client.post(
        "/api/gear",
        json={"name": "轰炸机 V02 锥形滤纸", "kind": "other", "brand": "轰炸机", "model": "V02"},
    ).json()
    packed = client.post(
        f"/api/gear/{other['id']}/packs",
        json={"sheets": 100, "price": 35},
    ).json()
    assert packed["kind"] == "filter"
    assert packed["kind_label"] == "滤纸"
    assert packed["sheets_left"] == 100
    assert packed["open_pack"]["unit_cost"] == pytest.approx(0.35)

    dripper = client.post("/api/gear", json={"name": "V60", "kind": "dripper"}).json()
    assert client.post(f"/api/gear/{dripper['id']}/packs", json={"sheets": 10}).status_code == 400


def test_two_open_packs_do_not_autopic(client):
    a = _paper(client, name="【测试】滤纸 A")
    b = _paper(client, name="【测试】滤纸 B")
    client.post(f"/api/gear/{a['id']}/packs", json={"sheets": 10, "price": 10})
    client.post(f"/api/gear/{b['id']}/packs", json={"sheets": 20, "price": 40})
    teaser = client.get("/api/brew/methods").json()["filter"]
    assert teaser["need_pick"] is True
    assert teaser["open_count"] == 2

    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    skip = client.post("/api/brews", json={"lot_id": lot, "amount_g": 16, "brew_method": "v60"}).json()
    assert skip["filter_cost"] is None
    assert client.get(f"/api/gear/{a['id']}").json()["sheets_left"] == 10
    assert client.get(f"/api/gear/{b['id']}").json()["sheets_left"] == 20

    pack_a = client.get(f"/api/gear/{a['id']}").json()["open_pack"]["id"]
    picked = client.post(
        "/api/brews",
        json={"lot_id": lot, "amount_g": 15, "brew_method": "v60", "filter_pack_id": pack_a},
    ).json()
    assert picked["filter_cost"] == pytest.approx(1)
    assert client.get(f"/api/gear/{a['id']}").json()["sheets_left"] == 9
    assert client.get(f"/api/gear/{b['id']}").json()["sheets_left"] == 20


def test_restock_only_after_counting_and_low(client):
    paper = _paper(client)
    assert client.get("/api/restock").json()["filters"] == []
    client.post(f"/api/gear/{paper['id']}/packs", json={"sheets": 21, "price": 21})
    assert client.get("/api/restock").json()["filters"] == []

    bean = new_bean(client)
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 16, "brew_method": "v60"})
    low = client.get("/api/restock").json()["filters"]
    assert len(low) == 1
    assert low[0]["sheets_left"] == 20
    assert "只剩 20 张" in low[0]["reasons"]

    for _ in range(20):
        client.post("/api/brews", json={"lot_id": lot, "amount_g": 1, "brew_method": "v60"})
    empty = client.get("/api/restock").json()["filters"]
    assert empty[0]["sheets_left"] == 0
    assert "用完了" in empty[0]["reasons"]


def test_plaza_take_filter_does_not_copy_packs(client):
    paper = _paper(client, visibility="public")
    client.post(f"/api/gear/{paper['id']}/packs", json={"sheets": 50, "price": 20})
    plaza = client.get(f"/api/public/gear/{paper['id']}").json()
    assert "packs" not in plaza
    assert "sheets_left" not in plaza

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "taker@coffeebar.local", "password": "testpass1"},
    )
    taken = client.post(f"/api/public/gear/{paper['id']}/take").json()
    assert taken["kind"] == "filter"
    assert taken["counting"] is False
    assert taken["packs"] == []
    assert taken["sheets_left"] == 0
