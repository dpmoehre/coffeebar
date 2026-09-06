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
    assert card["kind"] == "威士忌"
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

    lib = client.get("/api/spirits").json()
    assert lib["kinds"] == spirits.KINDS
    assert len(lib["spirits"]) == 1
    assert lib["spirits"][0]["last_price"] == 399
    assert lib["spirits"][0]["abv"] == 43
    assert lib["spirits"][0]["kind"] == "威士忌"


def test_kind_inferred_from_category(conn):
    make_spirit(conn)
    assert spirits.list_spirits(conn)[0]["kind"] == "威士忌"


def test_kind_explicit_gin(conn):
    bottle_id = spirits.create_spirit(
        conn, {"name": "Beefeater", "kind": "金酒", "category": "伦敦干金", "abv": 40}
    )
    assert spirits.get_spirit(conn, bottle_id)["kind"] == "金酒"


def test_normalize_kind_hints():
    assert spirits.normalize_kind(None, "单一麦芽威士忌") == "威士忌"
    assert spirits.normalize_kind(None, "伦敦干金") == "金酒"
    assert spirits.normalize_kind("金酒", "波本") == "金酒"
    assert spirits.normalize_kind(None, "梅斯卡尔") == "龙舌兰"
    assert spirits.normalize_kind(None, None, "无名瓶") == "其他"


def test_backfill_kinds_on_old_row(conn):
    conn.execute(
        "INSERT INTO bottle (name, category, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("老格兰杰", "单一麦芽威士忌", "2026-01-01 00:00:00", "2026-01-01 00:00:00"),
    )
    spirits.backfill_kinds(conn)
    assert conn.execute("SELECT kind FROM bottle WHERE name = '老格兰杰'").fetchone()[0] == "威士忌"


def _png():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (80, 50, 30)).save(buf, "PNG")
    return buf.getvalue()


def _make_spirit_api(client, name="【测试】金酒", ml=700, price=140.0, **extra):
    r = client.post(
        "/api/spirits",
        json={"name": name, "kind": "金酒", "abv": 40, "nominal_ml": ml, "price": price, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_delete_spirit_card(client):
    """建错的卡要能整张删掉。"""
    from app import db

    s = _make_spirit_api(client, name="【测试】演示酒")
    photo = client.post(
        f"/api/spirits/{s['id']}/photos",
        files={"file": ("pack.png", _png(), "image/png")},
        data={"kind": "pack"},
    ).json()
    name = photo["path"].split("/")[-1]
    assert (db.PHOTO_DIR / name).exists()

    r = client.delete(f"/api/spirits/{s['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "【测试】演示酒"
    assert client.get(f"/api/spirits/{s['id']}").status_code == 404
    assert client.get("/api/spirits?scope=all").json()["spirits"] == []
    assert not (db.PHOTO_DIR / name).exists(), "照片文件跟着清掉"
    assert client.get("/api/stats?period=all").json()["bought"] == 0


def test_delete_spirit_refuses_live_drinks(client):
    """有没撤回的倒酒时，不带 mode 仍拒删。"""
    s = _make_spirit_api(client)
    lot = s["lots"][0]["id"]
    drink = client.post("/api/drinks", json={"lot_id": lot, "amount_ml": 30}).json()

    r = client.delete(f"/api/spirits/{s['id']}")
    assert r.status_code == 409
    assert "花掉的钱" in r.json()["message"]
    assert client.get(f"/api/spirits/{s['id']}").status_code == 200

    client.post(f"/api/consumption/{drink['id']}/void", json={"reason": "记错了"})
    assert client.delete(f"/api/spirits/{s['id']}").status_code == 200


def test_delete_spirit_keep_spend(client):
    """真喝过：从酒库收起，统计里杯数和钱还在。"""
    s = _make_spirit_api(client, name="【测试】喝过的酒", ml=1000, price=399.0)
    lot = s["lots"][0]["id"]
    client.post("/api/drinks", json={"lot_id": lot, "amount_ml": 30})
    before = client.get("/api/stats", params={"period": "all"}).json()
    assert before["spent"] == pytest.approx(11.97)  # 30 × 399/1000
    assert before["on_hand"] == pytest.approx(387.03)  # 970 × 0.399
    assert before["drink_cups"] == 1

    r = client.delete(f"/api/spirits/{s['id']}", params={"mode": "keep"})
    assert r.status_code == 200, r.text
    assert r.json()["kept_spend"] is True
    assert client.get(f"/api/spirits/{s['id']}").status_code == 404
    assert client.get("/api/spirits?scope=all").json()["spirits"] == []

    after = client.get("/api/stats", params={"period": "all"}).json()
    assert after["spent"] == pytest.approx(before["spent"])
    assert after["bought"] == pytest.approx(before["bought"])
    assert after["on_hand"] == pytest.approx(0)
    assert after["drink_cups"] == 1
    assert after["drinks_ml"] == pytest.approx(30)


def test_delete_spirit_wipe_clears_spend(client):
    """建错的测试卡：连流水一起抹，统计里那几笔钱也没了。"""
    s = _make_spirit_api(client, name="【测试】抹掉的酒", ml=1000, price=399.0)
    lot = s["lots"][0]["id"]
    client.post("/api/drinks", json={"lot_id": lot, "amount_ml": 30})
    assert client.get("/api/stats", params={"period": "all"}).json()["spent"] > 0

    r = client.delete(f"/api/spirits/{s['id']}", params={"mode": "wipe"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/spirits/{s['id']}").status_code == 404
    after = client.get("/api/stats", params={"period": "all"}).json()
    assert after["spent"] == pytest.approx(0)
    assert after["bought"] == pytest.approx(0)
    assert after["drink_cups"] == 0


def test_delete_spirit_keeps_others(client):
    keep = _make_spirit_api(client, name="【测试】留着的酒")
    gone = _make_spirit_api(client, name="【测试】删掉的酒")
    assert client.delete(f"/api/spirits/{gone['id']}").status_code == 200
    names = [s["name"] for s in client.get("/api/spirits?scope=all").json()["spirits"]]
    assert names == ["【测试】留着的酒"]
    assert client.get(f"/api/spirits/{keep['id']}").status_code == 200


def test_delete_spirit_of_other_account(client):
    s = _make_spirit_api(client, name="【测试】A 的酒")
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "spiritnosy@coffeebar.local", "password": "testpass1"},
    )
    assert client.delete(f"/api/spirits/{s['id']}").status_code == 404


def test_delete_spirit_blocked_by_other_session(client):
    s = _make_spirit_api(client)
    client.post(
        f"/api/locks/bottle:{s['id']}",
        json={"holder": "另一台"},
        headers={"X-Session": "other"},
    )
    r = client.delete(f"/api/spirits/{s['id']}", headers={"X-Session": "mine"})
    assert r.status_code == 423


def test_delete_spirit_wipe_clears_menu_and_recipe(client):
    """酒单和配方引用这支酒时，wipe 不能被外键拦住。"""
    s = _make_spirit_api(client, name="【测试】酒单金")
    rec = client.post(
        "/api/recipes",
        json={"name": "【测试】金汤力", "lines": [{"spirit_id": s["id"], "amount_ml": 40}]},
    )
    assert rec.status_code == 201, rec.text
    listed = client.post("/api/menu", json={"kind": "neat", "spirit_id": s["id"]})
    assert listed.status_code == 201, listed.text
    cocktail = client.post("/api/menu", json={"kind": "cocktail", "recipe_id": rec.json()["id"]})
    assert cocktail.status_code == 201, cocktail.text

    r = client.delete(f"/api/spirits/{s['id']}")
    assert r.status_code == 200, r.text
    assert client.get("/api/menu").json()["items"] == []
    assert client.get("/api/recipes").json()["recipes"] == []


def test_delete_spirit_wipe_only_this_line_of_cocktail(client):
    """鸡尾酒一巡含两支：wipe 只抹这支的行，另一支流水还在。"""
    gin = _make_spirit_api(client, name="【测试】金酒甲", ml=700, price=140)
    bourbon = _make_spirit_api(client, name="【测试】波本乙", ml=700, price=210, kind="威士忌")
    rec = client.post(
        "/api/recipes",
        json={
            "name": "【测试】两支调",
            "lines": [
                {"spirit_id": gin["id"], "amount_ml": 30},
                {"spirit_id": bourbon["id"], "amount_ml": 20},
            ],
        },
    )
    assert rec.status_code == 201, rec.text
    item = client.post("/api/menu", json={"kind": "cocktail", "recipe_id": rec.json()["id"]})
    assert item.status_code == 201, item.text
    pour = client.post(
        "/api/menu/pour",
        json={
            "menu_item_id": item.json()["id"],
            "person": "丁瀚舟",
            "lines": [
                {"spirit_id": gin["id"], "lot_id": gin["lots"][0]["id"], "amount_ml": 40},
                {"spirit_id": bourbon["id"], "lot_id": bourbon["lots"][0]["id"], "amount_ml": 15},
            ],
        },
    )
    assert pour.status_code == 201, pour.text
    before = client.get("/api/stats", params={"period": "all"}).json()
    assert before["drink_cups"] == 1

    r = client.delete(f"/api/spirits/{gin['id']}", params={"mode": "wipe"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/spirits/{gin['id']}").status_code == 404
    assert client.get(f"/api/spirits/{bourbon['id']}").status_code == 200
    after = client.get("/api/stats", params={"period": "all"}).json()
    assert after["drink_cups"] == 1
    assert after["drinks_ml"] == pytest.approx(15)
    assert after["bought"] == pytest.approx(210)
    card = client.get(f"/api/spirits/{bourbon['id']}").json()
    assert card["balance_ml"] == pytest.approx(685)
