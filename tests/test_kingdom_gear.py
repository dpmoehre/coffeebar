"""王国器具：复用目录、总体分、收藏、广场对跳、注销留目录。"""

from app import db
from tests.test_photos import png_bytes


def _jpg():
    return {"file": ("cup.png", png_bytes(), "image/png")}


def _login(client, email, password="testpass1"):
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        return
    assert (
        client.post("/api/auth/register", json={"email": email, "password": password}).status_code
        == 201
    )


def _collect_gear(client, monkeypatch, name="Origami Air"):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    item = client.post(
        "/api/gear",
        json={"name": name, "kind": "dripper", "family": "cone", "visibility": "public"},
    ).json()
    client.post(f"/api/gear/{item['id']}/photos", files=_jpg())
    _login(client, "boss@coffeebar.local")
    cat = client.post(f"/api/admin/gear/{item['id']}/collect", json={"brew_method": "v60"}).json()[
        "catalog"
    ]
    _login(client, "test@coffeebar.local")
    return item, cat


def test_kingdom_gear_empty_until_catalog(client):
    assert client.get("/api/kingdom/gear").json()["gear"] == []


def test_collect_gear_appears_in_kingdom(client, monkeypatch):
    item, cat = _collect_gear(client, monkeypatch)
    listed = client.get("/api/kingdom/gear").json()["gear"]
    assert any(g["id"] == cat["id"] for g in listed)
    card = client.get(f"/api/kingdom/gear/{cat['id']}").json()
    assert card["name"] == "Origami Air"
    assert card["kind_label"] == "滤杯"
    assert card["reviews"] == 0
    assert card["scores"] == []
    assert "collected_by" not in card
    plaza = client.get(f"/api/public/gear/{item['id']}").json()
    assert plaza["kingdom"]["id"] == cat["id"]
    assert plaza["kingdom"]["reviews"] == 0


def test_one_person_one_review_and_favorite(client, monkeypatch):
    _, cat = _collect_gear(client, monkeypatch)
    cid = cat["id"]
    empty = client.put(f"/api/kingdom/gear/{cid}/score", json={})
    assert empty.status_code == 400

    wrote = client.put(
        f"/api/kingdom/gear/{cid}/score",
        json={"overall": 8.5, "comment": "水流稳"},
    )
    assert wrote.status_code == 200, wrote.text
    assert wrote.json()["mine"]["overall"] == 8.5
    assert wrote.json()["mine"]["author"].endswith("（我）")
    assert wrote.json()["avg"]["overall"] == 8.5

    again = client.put(
        f"/api/kingdom/gear/{cid}/score",
        json={"overall": 7, "comment": "改过了"},
    )
    assert again.json()["reviews"] == 1
    assert again.json()["mine"]["comment"] == "改过了"
    assert again.json()["avg"]["overall"] == 7

    fav = client.post(f"/api/kingdom/gear/{cid}/favorite")
    assert fav.json()["favorited"] is True
    saved = client.get("/api/kingdom/gear?saved=1").json()["gear"]
    assert [g["id"] for g in saved] == [cid]

    _login(client, "other@coffeebar.local")
    seen = client.get(f"/api/kingdom/gear/{cid}").json()
    assert seen["mine"] is None
    assert seen["scores"][0]["author"] == "test"
    assert seen["favorited"] is False
    client.put(f"/api/kingdom/gear/{cid}/score", json={"overall": 9})
    both = client.get(f"/api/kingdom/gear/{cid}").json()
    assert both["reviews"] == 2
    assert both["avg"]["overall"] == 8.0


def test_gear_review_photos_and_unscore(client, monkeypatch):
    _, cat = _collect_gear(client, monkeypatch)
    cid = cat["id"]
    bare = client.post(f"/api/kingdom/gear/{cid}/score/photos", files=_jpg())
    assert bare.status_code == 409

    client.put(f"/api/kingdom/gear/{cid}/score", json={"comment": "带图"})
    hung = client.post(f"/api/kingdom/gear/{cid}/score/photos", files=_jpg())
    assert hung.status_code == 201, hung.text
    photo_id = hung.json()["mine"]["photos"][0]["id"]
    name = hung.json()["mine"]["photos"][0]["path"].split("/")[-1]
    assert (db.PHOTO_DIR / name).exists()

    _login(client, "other@coffeebar.local")
    assert client.delete(f"/api/kingdom-gear-score-photos/{photo_id}").status_code == 403

    _login(client, "test@coffeebar.local")
    dropped = client.delete(f"/api/kingdom/gear/{cid}/score")
    assert dropped.status_code == 200
    assert dropped.json()["scores"] == []
    assert not (db.PHOTO_DIR / name).exists()


def test_delete_account_keeps_catalog_drops_review(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    item = client.post(
        "/api/gear",
        json={"name": "要注销的滤杯", "kind": "dripper", "family": "cone"},
    ).json()
    _login(client, "boss@coffeebar.local")
    cat = client.post(f"/api/admin/gear/{item['id']}/collect", json={}).json()["catalog"]
    _login(client, "reviewer@coffeebar.local")
    client.put(f"/api/kingdom/gear/{cat['id']}/score", json={"overall": 8, "comment": "会走"})
    client.post(f"/api/kingdom/gear/{cat['id']}/favorite")
    client.post(f"/api/kingdom/gear/{cat['id']}/score/photos", files=_jpg())
    card = client.get(f"/api/kingdom/gear/{cat['id']}").json()
    path = card["mine"]["photos"][0]["path"].split("/")[-1]
    assert (db.PHOTO_DIR / path).exists()

    gone = client.post(
        "/api/auth/delete",
        json={"email": "reviewer@coffeebar.local", "password": "testpass1"},
    )
    assert gone.status_code == 200, gone.text
    assert not (db.PHOTO_DIR / path).exists()

    _login(client, "boss@coffeebar.local")
    left = client.get(f"/api/kingdom/gear/{cat['id']}").json()
    assert left["name"] == "要注销的滤杯"
    assert left["scores"] == []
    assert left["favorites"] == 0
