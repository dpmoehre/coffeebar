"""咖啡王国：管理员收录、一人一豆杯测、收藏、注销留目录。"""

from app import db
from tests.test_photos import png_bytes


def _jpg():
    return {"file": ("bag.png", png_bytes(), "image/png")}


def _public_bean(client, name="【测试】MATYAZO", **extra):
    bean = client.post("/api/beans", json={"name": name, "origin": "卢旺达", **extra}).json()
    client.patch(f"/api/beans/{bean['id']}", json={"visibility": "public"})
    return bean


def _login(client, email, password="testpass1"):
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        return
    assert (
        client.post("/api/auth/register", json={"email": email, "password": password}).status_code
        == 201
    )


def test_ordinary_user_cannot_collect(client):
    bean = _public_bean(client)
    assert client.get("/api/admin/kingdom/queue").status_code == 403
    assert client.post(f"/api/admin/kingdom/collect/{bean['id']}", json={}).status_code == 403
    assert client.get("/api/kingdom").json()["beans"] == []


def test_collect_seeds_score_and_one_person_one_cup(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = _public_bean(client)
    scored = client.post(
        f"/api/beans/{bean['id']}/scores",
        json={"overall": 8, "acidity": 7, "comment": "黑莓可可"},
    )
    assert scored.status_code == 201, scored.text
    plaza = client.get(f"/api/public/beans/{bean['id']}").json()
    assert plaza.get("kingdom_id") in (None, 0)

    _login(client, "boss@coffeebar.local")
    queue = client.get("/api/admin/kingdom/queue").json()
    assert any(b["id"] == bean["id"] for b in queue["queue"])

    collected = client.post(f"/api/admin/kingdom/collect/{bean['id']}", json={"name": "MATYAZO CWS"})
    assert collected.status_code == 200, collected.text
    kid = collected.json()["id"]
    assert collected.json()["name"] == "MATYAZO CWS"
    assert collected.json()["cups"] == 1
    seed = collected.json()["scores"][0]
    assert seed["overall"] == 8
    assert seed["comment"] == "黑莓可可"
    assert "test" in seed["author"]

    empty = client.get("/api/admin/kingdom/queue").json()["queue"]
    assert all(b["id"] != bean["id"] for b in empty)
    assert client.post(f"/api/admin/kingdom/collect/{bean['id']}", json={}).status_code == 409

    _login(client, "test@coffeebar.local")
    public = client.get(f"/api/public/beans/{bean['id']}").json()
    assert public["kingdom_id"] == kid
    assert public["kingdom"]["id"] == kid
    assert public["kingdom"]["cups"] == 1
    assert public["kingdom"]["avg"]["overall"] == 8
    listed = client.get("/api/public/beans").json()["beans"]
    hit = next(b for b in listed if b["id"] == bean["id"])
    assert hit["kingdom"]["id"] == kid
    mine = client.get(f"/api/kingdom/{kid}").json()
    assert mine["plaza_cards"] == 1
    assert mine["mine"]["overall"] == 8
    assert mine["mine"]["author"].endswith("（我）")
    for key in ("unit_cost", "balance_g", "lots", "log", "owner_id"):
        assert key not in mine

    _login(client, "other@coffeebar.local")
    blank = client.put(f"/api/kingdom/{kid}/score", json={})
    assert blank.status_code == 400
    bad = client.put(f"/api/kingdom/{kid}/score", json={"overall": 11})
    assert bad.status_code == 400

    first = client.put(
        f"/api/kingdom/{kid}/score",
        json={"overall": 6, "sweetness": 7, "comment": "偏甜"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["cups"] == 2
    assert first.json()["mine"]["overall"] == 6
    assert first.json()["mine"]["author"].endswith("（我）")

    again = client.put(
        f"/api/kingdom/{kid}/score",
        json={"overall": 7, "sweetness": 8, "comment": "更甜了"},
    )
    assert again.json()["cups"] == 2
    assert again.json()["mine"]["overall"] == 7
    assert again.json()["mine"]["comment"] == "更甜了"

    dropped = client.delete(f"/api/kingdom/{kid}/score")
    assert dropped.status_code == 200
    assert dropped.json()["mine"] is None
    assert dropped.json()["cups"] == 1

    client.put(f"/api/kingdom/{kid}/score", json={"overall": 7, "comment": "回来了"})
    fav = client.post(f"/api/kingdom/{kid}/favorite", json={})
    assert fav.json()["favorited"] is True
    assert fav.json()["favorites"] == 1
    saved = client.get("/api/kingdom?saved=1").json()["beans"]
    assert [b["id"] for b in saved] == [kid]
    off = client.post(f"/api/kingdom/{kid}/favorite", json={})
    assert off.json()["favorited"] is False
    assert client.get("/api/kingdom?saved=1").json()["beans"] == []


def test_two_public_cards_share_one_kingdom(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    a = _public_bean(client, "【测试】MATYAZO 甲")
    _login(client, "second@coffeebar.local")
    b = _public_bean(client, "【测试】MATYAZO 乙")
    client.post(f"/api/beans/{b['id']}/scores", json={"overall": 9, "comment": "乙的杯测"})

    _login(client, "boss@coffeebar.local")
    first = client.post(f"/api/admin/kingdom/collect/{a['id']}", json={}).json()
    kid = first["id"]
    second = client.post(
        f"/api/admin/kingdom/collect/{b['id']}",
        json={"kingdom_id": kid},
    )
    assert second.status_code == 200, second.text
    card = second.json()
    assert card["id"] == kid
    assert {c["id"] for c in card["cards"]} == {a["id"], b["id"]}
    assert card["plaza_cards"] == 2
    assert card["cups"] == 1
    assert card["scores"][0]["overall"] == 9
    listed = client.get("/api/kingdom").json()["beans"]
    assert sum(1 for x in listed if x["id"] == kid) == 1


def test_private_bean_not_collectable(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    private = client.post("/api/beans", json={"name": "只自己看"}).json()
    _login(client, "boss@coffeebar.local")
    r = client.post(f"/api/admin/kingdom/collect/{private['id']}", json={})
    assert r.status_code == 400
    assert client.get("/api/admin/kingdom/queue").json()["queue"] == []


def test_delete_account_keeps_kingdom_drops_score(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = _public_bean(client)
    photo = client.post(f"/api/beans/{bean['id']}/photos", files=_jpg(), data={"kind": "pack"}).json()
    owner_name = photo["path"].split("/")[-1]

    _login(client, "boss@coffeebar.local")
    kid = client.post(f"/api/admin/kingdom/collect/{bean['id']}", json={}).json()["id"]
    cover = client.get(f"/api/kingdom/{kid}").json()["photos"][0]["path"].split("/")[-1]
    assert cover != owner_name
    assert (db.PHOTO_DIR / cover).exists()

    _login(client, "guest@coffeebar.local")
    client.put(f"/api/kingdom/{kid}/score", json={"overall": 5, "comment": "客人"})
    client.post(f"/api/kingdom/{kid}/favorite", json={})
    assert (
        client.post(
            "/api/auth/delete",
            json={"email": "guest@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 200
    )

    _login(client, "boss@coffeebar.local")
    card = client.get(f"/api/kingdom/{kid}").json()
    assert card["name"]
    assert card["cups"] == 0
    assert card["favorites"] == 0
    assert card["scores"] == []
    assert (db.PHOTO_DIR / cover).exists()


def test_admin_can_rename_kingdom(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = _public_bean(client)
    _login(client, "boss@coffeebar.local")
    kid = client.post(f"/api/admin/kingdom/collect/{bean['id']}", json={}).json()["id"]
    renamed = client.patch(f"/api/admin/kingdom/{kid}", json={"name": "改过的名字", "note": "管理员备注"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "改过的名字"
    assert renamed.json()["note"] == "管理员备注"
    _login(client, "other@coffeebar.local")
    assert client.patch(f"/api/admin/kingdom/{kid}", json={"name": "偷改"}).status_code == 403


def test_cupping_photos_stay_on_score(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = _public_bean(client)
    _login(client, "boss@coffeebar.local")
    kid = client.post(f"/api/admin/kingdom/collect/{bean['id']}", json={}).json()["id"]

    _login(client, "cupper@coffeebar.local")
    bare = client.post(f"/api/kingdom/{kid}/score/photos", files=_jpg())
    assert bare.status_code == 409

    client.put(f"/api/kingdom/{kid}/score", json={"overall": 8, "comment": "带图"})
    hung = client.post(f"/api/kingdom/{kid}/score/photos", files=_jpg())
    assert hung.status_code == 201, hung.text
    card = hung.json()
    assert len(card["mine"]["photos"]) == 1
    name = card["mine"]["photos"][0]["path"].split("/")[-1]
    assert (db.PHOTO_DIR / name).exists()
    listed = next(s for s in card["scores"] if s["mine"])
    assert listed["photos"][0]["id"] == card["mine"]["photos"][0]["id"]

    photo_id = card["mine"]["photos"][0]["id"]
    _login(client, "other@coffeebar.local")
    assert client.delete(f"/api/kingdom-score-photos/{photo_id}").status_code == 403

    _login(client, "cupper@coffeebar.local")
    for _ in range(7):
        assert client.post(f"/api/kingdom/{kid}/score/photos", files=_jpg()).status_code == 201
    ninth = client.post(f"/api/kingdom/{kid}/score/photos", files=_jpg())
    assert ninth.status_code == 400

    dropped = client.delete(f"/api/kingdom/{kid}/score")
    assert dropped.status_code == 200
    assert dropped.json()["mine"] is None
    assert not (db.PHOTO_DIR / name).exists()


def test_delete_account_drops_cupping_photos(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = _public_bean(client)
    _login(client, "boss@coffeebar.local")
    kid = client.post(f"/api/admin/kingdom/collect/{bean['id']}", json={}).json()["id"]

    _login(client, "guest@coffeebar.local")
    client.put(f"/api/kingdom/{kid}/score", json={"overall": 5, "comment": "客人带图"})
    shot = client.post(f"/api/kingdom/{kid}/score/photos", files=_jpg()).json()
    name = shot["mine"]["photos"][0]["path"].split("/")[-1]
    assert (db.PHOTO_DIR / name).exists()
    assert (
        client.post(
            "/api/auth/delete",
            json={"email": "guest@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 200
    )
    assert not (db.PHOTO_DIR / name).exists()
    _login(client, "boss@coffeebar.local")
    assert client.get(f"/api/kingdom/{kid}").json()["scores"] == []
