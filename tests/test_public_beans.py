"""公开豆卡去敏、认证审核、改关键字段掉认证。"""

from app.mcp_client import ApiError, Client


def test_default_private_not_on_plaza(client):
    bean = client.post("/api/beans", json={"name": "只自己看", "origin": "埃塞俄比亚"}).json()
    assert bean["visibility"] == "private"
    assert bean["certified"] is False
    plaza = client.get("/api/public/beans").json()["beans"]
    assert all(b["id"] != bean["id"] for b in plaza)
    assert client.get(f"/api/public/beans/{bean['id']}").status_code == 404


def test_public_card_hides_money_and_stock(client):
    bean = client.post(
        "/api/beans",
        json={"name": "公开耶加", "origin": "埃塞俄比亚", "nominal_g": 200, "price": 88},
    ).json()
    client.patch(f"/api/beans/{bean['id']}", json={"visibility": "public"})
    card = client.get(f"/api/public/beans/{bean['id']}").json()
    assert card["name"] == "公开耶加"
    assert card["origin"] == "埃塞俄比亚"
    assert card["certified"] is False
    assert card["mine"] is True
    for key in ("unit_cost", "balance_g", "lots", "log", "owner_id", "remaining_value"):
        assert key not in card
    plaza = client.get("/api/public/beans").json()["beans"]
    assert any(b["id"] == bean["id"] for b in plaza)
    hidden = client.get("/api/public/beans?certified=1").json()["beans"]
    assert all(b["id"] != bean["id"] for b in hidden)


def test_ordinary_user_cannot_certify(client):
    bean = client.post("/api/beans", json={"name": "待审", "origin": "埃塞俄比亚"}).json()
    client.patch(f"/api/beans/{bean['id']}", json={"visibility": "public"})
    assert client.post(f"/api/admin/review/beans/{bean['id']}/certify", json={}).status_code == 403
    assert client.get("/api/admin/review/beans").status_code == 403


def test_admin_certify_and_filter(client, monkeypatch):
    bean = client.post(
        "/api/beans",
        json={"name": "西达摩水洗", "origin": "埃塞俄比亚 西达玛", "process": "水洗"},
    ).json()
    client.patch(f"/api/beans/{bean['id']}", json={"visibility": "public"})
    owner_id = client.get("/api/me").json()["id"]

    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/register",
            json={"email": "boss@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 201
    )

    queue = client.get("/api/admin/review/beans").json()["beans"]
    assert any(b["id"] == bean["id"] for b in queue)
    review = client.get(f"/api/admin/review/beans/{bean['id']}").json()
    assert review["owner"]["id"] == owner_id
    assert "places" in review
    assert "gazetteer" in review["places"]
    assert "unit_cost" not in review

    out = client.post(
        f"/api/admin/review/beans/{bean['id']}/certify",
        json={"note": "产地和钉对得上"},
    )
    assert out.status_code == 200, out.text
    assert out.json()["certified"] is True

    plaza = client.get("/api/public/beans?certified=1").json()["beans"]
    assert any(b["id"] == bean["id"] and b["certified"] for b in plaza)


def test_identity_change_drops_cert(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = client.post(
        "/api/beans",
        json={"name": "要改产地", "origin": "埃塞俄比亚", "visibility": "public"},
    ).json()
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    assert client.post(f"/api/admin/review/beans/{bean['id']}/certify", json={}).status_code == 200
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"email": "test@coffeebar.local", "password": "testpass1"},
    )
    patched = client.patch(f"/api/beans/{bean['id']}", json={"origin": "肯尼亚"})
    assert patched.status_code == 200
    assert patched.json()["certified"] is False
    assert patched.json().get("certification_dropped") is True
    card = client.get(f"/api/public/beans/{bean['id']}").json()
    assert card["certified"] is False
    assert card["origin"] == "肯尼亚"


def test_private_again_drops_cert(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = client.post(
        "/api/beans",
        json={"name": "收回去", "origin": "哥伦比亚", "visibility": "public"},
    ).json()
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    client.post(f"/api/admin/review/beans/{bean['id']}/certify", json={"force_places": True})
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"email": "test@coffeebar.local", "password": "testpass1"},
    )
    out = client.patch(f"/api/beans/{bean['id']}", json={"visibility": "private"})
    assert out.json()["certified"] is False
    assert client.get(f"/api/public/beans/{bean['id']}").status_code == 404


def test_certify_refuses_bad_places_until_forced(client, monkeypatch):
    bean = client.post("/api/beans", json={"name": "无钉", "visibility": "public"}).json()
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    refused = client.post(f"/api/admin/review/beans/{bean['id']}/certify", json={})
    assert refused.status_code == 409
    assert "places" in refused.json()
    forced = client.post(
        f"/api/admin/review/beans/{bean['id']}/certify",
        json={"force_places": True, "note": "手校过，词典没有"},
    )
    assert forced.status_code == 200, forced.text
    assert forced.json()["certified"] is True


def test_mcp_review_tools_need_admin(client, monkeypatch):
    bean = client.post(
        "/api/beans",
        json={"name": "MCP审", "origin": "埃塞俄比亚", "visibility": "public"},
    ).json()
    c = Client.from_test(client)
    try:
        c.list_review_queue()
        raise AssertionError("普通人不应看到待审")
    except ApiError as exc:
        assert exc.status == 403

    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    admin = Client.from_test(client)
    queue = admin.list_review_queue("pending")
    assert any(b["id"] == bean["id"] for b in queue["beans"])
    detail = admin.get_review_bean(bean["id"])
    assert detail["places"]["gazetteer"]
    certified = admin.certify_bean(bean["id"], note="MCP 过了")
    assert certified["certified"] is True
    dropped = admin.uncertify_bean(bean["id"], note="再看一眼")
    assert dropped["certified"] is False
