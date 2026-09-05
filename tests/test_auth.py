"""账号与归属：A 看不到 B 的豆、酒、钱。"""

from app import auth, spirits, store


def test_register_and_me(client):
    me = client.get("/api/me").json()
    assert me["email"] == "test@coffeebar.local"


def test_beans_require_login(client):
    from fastapi.testclient import TestClient

    bare = TestClient(client.app)
    assert bare.get("/api/beans").status_code == 401


def test_b_cannot_see_a_bean(client):
    a = client.post("/api/beans", json={"name": "A 的豆", "nominal_g": 200, "price": 80}).json()
    assert client.get("/api/beans").json()["beans"][0]["name"] == "A 的豆"
    assert client.get(f"/api/beans/{a['id']}").status_code == 200

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "b@coffeebar.local", "password": "testpass1"},
    )
    lib = client.get("/api/beans").json()["beans"]
    assert lib == []
    assert client.get(f"/api/beans/{a['id']}").status_code == 404
    stats = client.get("/api/stats?period=all").json()
    assert stats["bought"] == 0
    assert stats["on_hand"] == 0


def test_b_cannot_see_a_spirit(client):
    s = client.post(
        "/api/spirits",
        json={"name": "A 的酒", "kind": "威士忌", "abv": 40, "nominal_ml": 700, "price": 199},
    ).json()
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "c@coffeebar.local", "password": "testpass1"},
    )
    assert client.get("/api/spirits").json()["spirits"] == []
    assert client.get(f"/api/spirits/{s['id']}").status_code == 404


def test_first_account_claims_orphans(conn):
    store.create_bean(conn, {"name": "老豆"})
    spirits.create_spirit(conn, {"name": "老酒", "category": "单一麦芽威士忌"})
    store.ensure_person(conn, "戚浩辰")
    out = auth.register(conn, "owner@coffeebar.local", "testpass1")
    assert out["claimed"] is True
    assert store.list_beans(conn, owner_id=out["id"])[0]["name"] == "老豆"
    assert spirits.list_spirits(conn, owner_id=out["id"])[0]["name"] == "老酒"
    assert store.list_people(conn, owner_id=out["id"])[0]["name"] == "戚浩辰"

    other = auth.register(conn, "other@coffeebar.local", "testpass1")
    assert other["claimed"] is False
    assert store.list_beans(conn, owner_id=other["id"]) == []
