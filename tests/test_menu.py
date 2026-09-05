"""推荐酒单：纯饮 / 鸡尾酒一巡、杯数去重、多瓶不自挑、占锁硬拒。"""

from app import locks, menu, spirits, stats, store
from tests.test_spirits import make_spirit


def _item(conn, bottle_id, **kw):
    return menu.add_menu_item(conn, {"owner_id": None, "kind": "neat", "spirit_id": bottle_id, **kw})


def test_neat_pour_deducts_and_counts_one_cup(conn):
    bottle_id, lot_id = make_spirit(conn)
    item = _item(conn, bottle_id)
    serve = menu.pour(conn, {"menu_item_id": item["id"], "person": "丁瀚舟", "lines": [
        {"spirit_id": bottle_id, "lot_id": lot_id, "amount_ml": 35}
    ]})
    assert serve["kind"] == "neat"
    assert serve["name"] == "格兰杰 谜 16年"
    assert serve["amount_ml"] == 35
    assert spirits.get_lot(conn, lot_id)["balance_ml"] == 965
    s = stats.summary(conn, "all")
    assert s["drink_cups"] == 1
    assert s["drinks_ml"] == 35


def test_cocktail_two_spirits_is_one_cup(conn):
    gin_id, gin_lot = make_spirit(conn, name="【测试】金酒", ml=700, price=140, abv=40)
    whiskey_id, whiskey_lot = make_spirit(conn, name="【测试】波本", ml=700, price=210, abv=45)
    rec = menu.create_recipe(
        conn,
        {
            "owner_id": None,
            "name": "【测试】自由古巴",
            "lines": [
                {"spirit_id": gin_id, "amount_ml": 30},
                {"spirit_id": whiskey_id, "amount_ml": 20},
            ],
        },
    )
    item = menu.add_menu_item(conn, {"owner_id": None, "kind": "cocktail", "recipe_id": rec["id"]})
    serve = menu.pour(
        conn,
        {
            "menu_item_id": item["id"],
            "person": "戚浩辰",
            "lines": [
                {"spirit_id": gin_id, "lot_id": gin_lot, "amount_ml": 40},
                {"spirit_id": whiskey_id, "lot_id": whiskey_lot, "amount_ml": 15},
            ],
        },
    )
    assert serve["kind"] == "cocktail"
    assert len(serve["lines"]) == 2
    assert serve["amount_ml"] == 55
    assert spirits.get_lot(conn, gin_lot)["balance_ml"] == 660
    assert spirits.get_lot(conn, whiskey_lot)["balance_ml"] == 685
    assert stats.summary(conn, "all")["drink_cups"] == 1


def test_multi_lot_refuses_to_pick(conn):
    bottle_id, _ = make_spirit(conn)
    spirits.add_lot(conn, bottle_id, {"nominal_ml": 700, "price": 200})
    item = _item(conn, bottle_id)
    out = menu.pour(conn, {"menu_item_id": item["id"], "lines": [{"spirit_id": bottle_id, "amount_ml": 30}]})
    assert out["error"]
    assert len(out["needs"][0]["lots"]) == 2
    assert spirits.get_lot(conn, out["needs"][0]["lots"][0]["lot_id"])["balance_ml"] == 1000


def test_web_lock_rejects_whole_serve(conn):
    bottle_id, lot_id = make_spirit(conn)
    item = _item(conn, bottle_id)
    locks.acquire(conn, f"bottle:{bottle_id}", "web1", holder="小主机", source="web")
    try:
        menu.pour(
            conn,
            {"menu_item_id": item["id"], "lines": [{"spirit_id": bottle_id, "lot_id": lot_id, "amount_ml": 30}]},
            session_id="mcp",
            source="mcp",
        )
        raise AssertionError("should lock")
    except locks.Locked:
        pass
    assert spirits.get_lot(conn, lot_id)["balance_ml"] == 1000


def test_void_serve_restores_both_bottles(conn):
    a_id, a_lot = make_spirit(conn, name="【测试】A", ml=500, price=100, abv=40)
    b_id, b_lot = make_spirit(conn, name="【测试】B", ml=500, price=100, abv=40)
    rec = menu.create_recipe(
        conn,
        {
            "owner_id": None,
            "name": "【测试】双酒",
            "lines": [{"spirit_id": a_id, "amount_ml": 20}, {"spirit_id": b_id, "amount_ml": 20}],
        },
    )
    item = menu.add_menu_item(conn, {"owner_id": None, "kind": "cocktail", "recipe_id": rec["id"]})
    serve = menu.pour(
        conn,
        {
            "menu_item_id": item["id"],
            "lines": [
                {"spirit_id": a_id, "lot_id": a_lot, "amount_ml": 20},
                {"spirit_id": b_id, "lot_id": b_lot, "amount_ml": 20},
            ],
        },
    )
    store.void_consumption(conn, serve["lines"][0]["id"], "MCP测试")
    assert spirits.get_lot(conn, a_lot)["balance_ml"] == 500
    assert spirits.get_lot(conn, b_lot)["balance_ml"] == 500
    assert stats.summary(conn, "all")["drink_cups"] == 0


def test_old_card_pour_still_one_cup(conn):
    _, lot_id = make_spirit(conn)
    spirits.record_drink(conn, {"lot_id": lot_id, "amount_ml": 30})
    bottle_id, lot2 = make_spirit(conn, name="【测试】另一瓶", ml=700, price=70, abv=40)
    item = _item(conn, bottle_id)
    menu.pour(conn, {"menu_item_id": item["id"], "lines": [{"spirit_id": bottle_id, "lot_id": lot2, "amount_ml": 25}]})
    assert stats.summary(conn, "all")["drink_cups"] == 2


def test_unlist_hidden_from_listed_only(conn):
    bottle_id, _ = make_spirit(conn)
    item = _item(conn, bottle_id)
    menu.set_listed(conn, item["id"], False)
    assert menu.list_menu(conn, None, listed_only=True) == []
    assert len(menu.list_menu(conn, None, listed_only=False)) == 1


def test_other_account_cannot_see(client):
    a = client.post(
        "/api/spirits",
        json={"name": "【测试】菜单金", "kind": "金酒", "abv": 40, "nominal_ml": 700, "price": 80},
    ).json()
    rec = client.post(
        "/api/recipes",
        json={"name": "【测试】金加金", "lines": [{"spirit_id": a["id"], "amount_ml": 30}]},
    )
    assert rec.status_code == 201, rec.text
    listed = client.post("/api/menu", json={"kind": "cocktail", "recipe_id": rec.json()["id"]})
    assert listed.status_code == 201, listed.text
    pour = client.post(
        "/api/menu/pour",
        json={
            "menu_item_id": listed.json()["id"],
            "person": "丁瀚舟",
            "lines": [{"spirit_id": a["id"], "lot_id": a["lots"][0]["id"], "amount_ml": 30}],
        },
    )
    assert pour.status_code == 201, pour.text
    assert pour.json()["amount_ml"] == 30
    cal = client.get("/api/calendar/day", params={"date": pour.json()["at"][:10]}).json()
    drinks = [e for e in cal["events"] if e["kind"] == "drink"]
    assert len(drinks) == 1
    assert drinks[0]["name"] == "【测试】金加金"
    assert drinks[0]["amount_ml"] == 30
    assert client.get("/api/stats", params={"period": "all"}).json()["drink_cups"] == 1

    locked = client.post(
        f"/api/locks/recipe:{rec.json()['id']}",
        json={"holder": "网页"},
        headers={"X-Session": "web1", "X-Source": "web"},
    )
    assert locked.status_code == 200, locked.text
    blocked = client.patch(
        f"/api/recipes/{rec.json()['id']}",
        json={"name": "不该改成这样"},
        headers={"X-Session": "mcp", "X-Source": "mcp"},
    )
    assert blocked.status_code == 423

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "other@coffeebar.local", "password": "testpass1"})
    assert client.get("/api/menu").json()["items"] == []
    assert client.get("/api/recipes").json()["recipes"] == []
