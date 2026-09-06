"""公开豆卡去敏、认证审核、改关键字段掉认证。"""

import pytest

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
    assert card.get("kingdom") in (None, {})
    assert card["offer"]["price"] == 88
    assert card["offer"]["nominal_g"] == 200
    assert card["offer"]["per_g"] == pytest.approx(88 / 200)
    for key in ("unit_cost", "balance_g", "lots", "log", "owner_id", "remaining_value", "price"):
        assert key not in card
    plaza = client.get("/api/public/beans").json()["beans"]
    hit = next(b for b in plaza if b["id"] == bean["id"])
    assert hit["offer"]["price"] == 88
    assert hit["offer"]["nominal_g"] == 200
    assert hit["offer"]["per_g"] == pytest.approx(88 / 200)
    hidden = client.get("/api/public/beans?certified=1").json()["beans"]
    assert all(b["id"] != bean["id"] for b in hidden)


def test_plaza_sorts_cost_roast_origin(client):
    cheap = client.post(
        "/api/beans",
        json={
            "name": "排哥伦比亚深烘",
            "origin": "哥伦比亚",
            "roast": "深烘",
            "nominal_g": 200,
            "price": 60,
            "visibility": "public",
        },
    ).json()
    mid = client.post(
        "/api/beans",
        json={
            "name": "排肯尼亚中烘",
            "origin": "肯尼亚",
            "roast": "中烘",
            "nominal_g": 200,
            "price": 80,
            "visibility": "public",
        },
    ).json()
    dear = client.post(
        "/api/beans",
        json={
            "name": "排埃塞浅烘",
            "origin": "埃塞俄比亚",
            "roast": "浅烘",
            "nominal_g": 200,
            "price": 100,
            "visibility": "public",
        },
    ).json()
    want = {cheap["id"], mid["id"], dear["id"]}

    def ids(sort):
        rows = client.get(f"/api/public/beans?sort={sort}").json()["beans"]
        return [b["id"] for b in rows if b["id"] in want]

    assert ids("cost") == [cheap["id"], mid["id"], dear["id"]]
    assert ids("cost_desc") == [dear["id"], mid["id"], cheap["id"]]
    assert ids("price") == [cheap["id"], mid["id"], dear["id"]]
    assert ids("roast") == [dear["id"], mid["id"], cheap["id"]]
    assert ids("origin") == [cheap["id"], dear["id"], mid["id"]]


def test_plaza_filters_roast_tag_and_kingdom(client, monkeypatch):
    wash = client.post(
        "/api/beans",
        json={
            "name": "筛浅烘水洗",
            "origin": "埃塞俄比亚",
            "roast": "浅烘",
            "process": "水洗",
            "tags": ["柑橘", "耶加"],
            "visibility": "public",
            "nominal_g": 200,
            "price": 88,
        },
    ).json()
    mid = client.post(
        "/api/beans",
        json={
            "name": "筛中烘日晒",
            "origin": "哥伦比亚",
            "roast": "中烘",
            "process": "日晒",
            "tags": ["巧克力"],
            "visibility": "public",
        },
    ).json()
    sun = client.post(
        "/api/beans",
        json={
            "name": "筛浅烘日晒",
            "roast": "浅烘",
            "process": "日晒",
            "tags": ["柑橘"],
            "visibility": "public",
        },
    ).json()

    roast_ids = {b["id"] for b in client.get("/api/public/beans?roast=浅烘").json()["beans"]}
    assert {wash["id"], sun["id"]} <= roast_ids
    assert mid["id"] not in roast_ids

    both = {b["id"] for b in client.get("/api/public/beans?roast=浅烘，中烘").json()["beans"]}
    assert {wash["id"], mid["id"], sun["id"]} <= both

    tag_ids = {b["id"] for b in client.get("/api/public/beans?tag=柑橘,耶加").json()["beans"]}
    assert wash["id"] in tag_ids
    assert sun["id"] not in tag_ids
    assert mid["id"] not in tag_ids

    q_ids = {b["id"] for b in client.get("/api/public/beans?q=哥伦比亚").json()["beans"]}
    assert mid["id"] in q_ids
    assert wash["id"] not in q_ids

    process_ids = {b["id"] for b in client.get("/api/public/beans?process=水洗").json()["beans"]}
    assert wash["id"] in process_ids
    assert mid["id"] not in process_ids

    listed = client.get("/api/public/beans").json()["beans"]
    money = next(b for b in listed if b["id"] == wash["id"])
    assert money["offer"]["price"] == 88
    assert money["offer"]["nominal_g"] == 200
    for key in ("unit_cost", "balance_g", "lots", "price", "remaining_value"):
        assert key not in money

    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/register",
            json={"email": "boss@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 201
    )
    collected = client.post(f"/api/admin/kingdom/collect/{wash['id']}", json={"name": "筛选王国"})
    assert collected.status_code == 200, collected.text

    in_k = {b["id"] for b in client.get("/api/public/beans?in_kingdom=1").json()["beans"]}
    assert wash["id"] in in_k
    assert mid["id"] not in in_k
    out_k = {b["id"] for b in client.get("/api/public/beans?in_kingdom=0").json()["beans"]}
    assert mid["id"] in out_k
    assert wash["id"] not in out_k


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
    assert "lots" not in review
    assert "balance_g" not in review
    assert "log" not in review
    assert review["price"] is None
    assert review["checklist"]["origin"] is True
    assert review["checklist"]["photos"] is False
    assert review["checklist"]["scores"] is False
    assert review["checklist"]["note"] is False
    assert review["checklist"]["price"] is False

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
    assert "checklist" in detail
    certified = admin.certify_bean(bean["id"], note="MCP 过了")
    assert certified["certified"] is True
    dropped = admin.uncertify_bean(bean["id"], note="再看一眼")
    assert dropped["certified"] is False


def test_review_dossier_shows_archive_not_stock(client, monkeypatch):
    from tests.test_photos import png_bytes

    bean = client.post(
        "/api/beans",
        json={
            "name": "档案完整",
            "origin": "埃塞俄比亚 耶加雪菲",
            "varietal": "Heirloom",
            "process": "水洗",
            "roast": "中浅",
            "note": "店家说有茉莉和柠檬皮",
            "nominal_g": 200,
            "price": 88,
            "visibility": "public",
        },
    ).json()
    client.post(
        f"/api/beans/{bean['id']}/scores",
        json={
            "dry": 8,
            "flavor": 8,
            "aftertaste": 7,
            "acidity": 8,
            "sweetness": 7,
            "body": 6,
            "balance": 7,
            "overall": 8,
            "comment": "茉莉",
        },
    )
    photo = client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("pack.png", png_bytes(), "image/png")},
        data={"kind": "pack"},
    )
    assert photo.status_code == 201, photo.text

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
    item = next(b for b in queue if b["id"] == bean["id"])
    assert item["checklist"]["photos"] is True
    assert item["checklist"]["scores"] is True
    assert item["checklist"]["note"] is True
    assert item["checklist"]["price"] is True
    assert item["price"]["price"] == 88

    review = client.get(f"/api/admin/review/beans/{bean['id']}").json()
    assert review["note"].startswith("店家")
    assert review["scores"]["comment"] == "茉莉"
    assert review["photos"]
    assert review["price"]["price"] == 88
    assert review["price"]["nominal_g"] == 200
    assert review["checklist"] == {
        "photos": True,
        "scores": True,
        "note": True,
        "price": True,
        "origin": True,
        "places": True,
    }
    for key in ("lots", "balance_g", "log", "unit_cost"):
        assert key not in review


def test_take_public_bean_copies_archive_without_lots(client):
    from tests.test_photos import png_bytes

    bean = client.post(
        "/api/beans",
        json={
            "name": "领回耶加",
            "origin": "埃塞俄比亚",
            "roast": "浅烘",
            "process": "水洗",
            "tags": ["柑橘"],
            "nominal_g": 200,
            "price": 88,
            "visibility": "public",
        },
    ).json()
    photo = client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("pack.png", png_bytes(), "image/png")},
        data={"kind": "pack"},
    )
    assert photo.status_code == 201, photo.text
    src_path = photo.json()["path"]
    card = client.get(f"/api/public/beans/{bean['id']}").json()
    assert card["mine"] is True
    assert card["taken"] is False
    own = client.post(f"/api/public/beans/{bean['id']}/take", json={})
    assert own.status_code == 400

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "taker@coffeebar.local", "password": "testpass1"},
    )
    plaza = client.get(f"/api/public/beans/{bean['id']}").json()
    assert plaza["taken"] is False
    assert plaza["offer"]["price"] == 88
    for key in ("lots", "balance_g", "log", "owner_id", "unit_cost"):
        assert key not in plaza

    first = client.post(f"/api/public/beans/{bean['id']}/take", json={})
    assert first.status_code == 200, first.text
    cloned = first.json()
    assert cloned["id"] != bean["id"]
    assert cloned["name"] == "领回耶加"
    assert cloned["source_bean_id"] == bean["id"]
    assert cloned["lots"] == []
    assert cloned["balance_g"] == 0
    assert cloned.get("certified") is False
    assert cloned["visibility"] == "private"

    detail = client.get(f"/api/beans/{cloned['id']}").json()
    assert detail["lots"] == []
    assert detail["log"] == []
    assert detail["photos"]
    assert detail["photos"][0]["path"] != src_path
    for key in ("unit_cost", "remaining_value"):
        assert not detail.get(key)

    again = client.post(f"/api/public/beans/{bean['id']}/take", json={}).json()
    assert again["id"] == cloned["id"]
    flagged = client.get(f"/api/public/beans/{bean['id']}").json()
    assert flagged["taken"] is True
    assert flagged["cloned_id"] == cloned["id"]


def test_take_private_bean_is_404(client):
    bean = client.post("/api/beans", json={"name": "不给领"}).json()
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "nosy@coffeebar.local", "password": "testpass1"},
    )
    assert client.get(f"/api/public/beans/{bean['id']}").status_code == 404
    assert client.post(f"/api/public/beans/{bean['id']}/take", json={}).status_code == 404
