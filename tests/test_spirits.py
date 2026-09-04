"""基酒：入库、克价（元/毫升）、倒一杯、同酒多瓶一张卡。"""

import pytest

from app import spirits, stats, store


def make_spirit(conn, name="格兰杰 谜 16年", ml=1000, price=399.0, abv=43.0):
    bottle_id = spirits.create_spirit(
        conn,
        {
            "name": name,
            "category": "单一麦芽威士忌",
            "origin": "苏格兰高地",
            "abv": abv,
            "flavor": "柑橘甜、圆润、一丝烟熏",
            "tags": ["柑橘", "波本桶", "高地"],
        },
    )
    lot_id = spirits.add_lot(conn, bottle_id, {"nominal_ml": ml, "price": price})
    return bottle_id, lot_id


def test_create_spirit_lists_name_price_flavor_abv(conn):
    make_spirit(conn)
    card = spirits.list_spirits(conn)[0]
    assert card["name"] == "格兰杰 谜 16年"
    assert card["last_price"] == 399
    assert card["flavor"] == "柑橘甜、圆润、一丝烟熏"
    assert card["abv"] == 43
    assert card["balance_ml"] == 1000
    assert card["unit_cost"] == pytest.approx(0.399)


def test_pour_deducts_ml_and_freezes_cost(conn):
    _, lot_id = make_spirit(conn)
    out = spirits.record_drink(conn, {"lot_id": lot_id, "amount_ml": 30, "person": "丁瀚舟"})
    assert out["balance_ml"] == pytest.approx(970)
    assert out["cost"] == pytest.approx(30 * 0.399)
    assert out["alcohol_g"] == pytest.approx(spirits.alcohol_g(30, 43))

    lot = spirits.get_lot(conn, lot_id)
    assert lot["opened_on"] is not None, "第一杯顺便记开瓶日"


def test_second_bottle_is_same_card(conn):
    bottle_id, _ = make_spirit(conn)
    spirits.add_lot(conn, bottle_id, {"nominal_ml": 1000, "price": 399})
    assert len(spirits.list_spirits(conn)) == 1
    d = spirits.get_spirit(conn, bottle_id)
    assert [l["seq"] for l in d["lots"]] == [1, 2]
    assert d["balance_ml"] == pytest.approx(2000)


def test_cannot_overpour(conn):
    _, lot_id = make_spirit(conn, ml=40)
    with pytest.raises(store.Conflict, match="不够"):
        spirits.record_drink(conn, {"lot_id": lot_id, "amount_ml": 50})


def test_void_drink_returns_ml(conn):
    _, lot_id = make_spirit(conn)
    pour = spirits.record_drink(conn, {"lot_id": lot_id, "amount_ml": 40})
    store.void_consumption(conn, pour["id"], "记错了")
    assert spirits.get_lot(conn, lot_id)["balance_ml"] == pytest.approx(1000)


def test_stats_bought_includes_bottles(conn):
    make_spirit(conn)
    s = stats.summary(conn, "all")
    assert s["bought"] == pytest.approx(399)
    assert s["on_hand"] == pytest.approx(399)
    assert s["drinks_ml"] == 0


def test_stats_drink_spent_and_alcohol(conn):
    _, lot_id = make_spirit(conn)
    spirits.record_drink(conn, {"lot_id": lot_id, "amount_ml": 30})
    s = stats.summary(conn, "all")
    assert s["drinks_ml"] == pytest.approx(30)
    assert s["drink_cups"] == 1
    assert s["alcohol_g"] == pytest.approx(round(30 * 0.43 * 0.789, 1))
    assert s["spent"] == pytest.approx(30 * 0.399)
    assert s["on_hand"] == pytest.approx(970 * 0.399)


def test_create_via_api(client):
    r = client.post(
        "/api/spirits",
        json={
            "name": "格兰杰 谜 16年",
            "category": "单一麦芽威士忌",
            "abv": 43,
            "flavor": "柑橘甜、圆润、一丝烟熏",
            "nominal_ml": 1000,
            "price": 399,
        },
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["balance_ml"] == 1000
    assert d["lots"][0]["unit_cost"] == pytest.approx(0.399)

    lib = client.get("/api/spirits").json()["spirits"]
    assert len(lib) == 1
    assert lib[0]["last_price"] == 399
    assert lib[0]["abv"] == 43
