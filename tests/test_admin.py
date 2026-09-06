"""管理员能看所有人的库；普通人仍然 403。"""

from app import auth


def test_default_admin_email():
    assert auth.is_admin_email("1821601734@qq.com")
    assert auth.is_admin_email("1821601734@QQ.com")
    assert not auth.is_admin_email("test@coffeebar.local")


def test_ordinary_user_cannot_open_admin(client):
    assert client.get("/api/me").json()["admin"] is False
    assert client.get("/api/admin/accounts").status_code == 403


def test_admin_sees_other_account_beans_and_drinks(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = client.post(
        "/api/beans",
        json={"name": "别人的豆", "nominal_g": 200, "price": 80},
    ).json()
    lot = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot, "amount_g": 16, "person": "丁瀚舟"})
    spirit = client.post(
        "/api/spirits",
        json={"name": "别人的酒", "kind": "金酒", "abv": 40, "nominal_ml": 700, "price": 90},
    ).json()
    client.post(
        "/api/drinks",
        json={"lot_id": spirit["lots"][0]["id"], "amount_ml": 30, "person": "丁瀚舟"},
    )

    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/register",
            json={"email": "boss@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 201
    )
    me = client.get("/api/me").json()
    assert me["admin"] is True

    accounts = client.get("/api/admin/accounts").json()["accounts"]
    other = next(a for a in accounts if a["email"] == "test@coffeebar.local")
    assert other["beans"] == 1
    assert other["spirits"] == 1
    assert other["cups"] >= 1

    dossier = client.get(f"/api/admin/accounts/{other['id']}").json()
    assert [b["name"] for b in dossier["beans"]] == ["别人的豆"]
    assert [s["name"] for s in dossier["spirits"]] == ["别人的酒"]
    names = {c.get("bean_name") or c.get("spirit_name") for c in dossier["consumption"]}
    assert "别人的豆" in names
    assert "别人的酒" in names

    card = client.get(f"/api/admin/accounts/{other['id']}/beans/{bean['id']}").json()
    assert card["name"] == "别人的豆"
    assert card["log"]

    bottle = client.get(f"/api/admin/accounts/{other['id']}/spirits/{spirit['id']}").json()
    assert bottle["name"] == "别人的酒"


def test_admin_can_disable_and_not_self(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    accounts = client.get("/api/admin/accounts").json()["accounts"]
    other = next(a for a in accounts if a["email"] == "test@coffeebar.local")
    boss = next(a for a in accounts if a["email"] == "boss@coffeebar.local")

    assert client.patch(f"/api/admin/accounts/{boss['id']}", json={"status": "disabled"}).status_code == 400
    out = client.patch(f"/api/admin/accounts/{other['id']}", json={"status": "disabled"})
    assert out.status_code == 200
    assert out.json()["status"] == "disabled"

    client.post("/api/auth/logout")
    denied = client.post(
        "/api/auth/login",
        json={"email": "test@coffeebar.local", "password": "testpass1"},
    )
    assert denied.status_code == 401

    client.post(
        "/api/auth/login",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    client.patch(f"/api/admin/accounts/{other['id']}", json={"status": "active"})
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "test@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 200
    )


def test_admin_cannot_see_via_normal_api(client, monkeypatch):
    """后台另开接口。普通 /api/beans 仍只出自己的，避免管理员一登录豆库就混在一起。"""
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    client.post("/api/beans", json={"name": "A 豆", "nominal_g": 100})
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    names = [b["name"] for b in client.get("/api/beans").json()["beans"]]
    assert "A 豆" not in names
