"""私人器具、管理员收录、按滤杯给冲煮建议。"""

from app import db
from tests.test_photos import png_bytes


def _jpg():
    return {"file": ("cup.png", png_bytes(), "image/png")}


def test_gear_is_private_and_methods_follow_dripper(client):
    cone = client.post(
        "/api/gear",
        json={"name": "我的 V60", "kind": "dripper", "family": "cone"},
    ).json()
    assert cone["kind_label"] == "滤杯"
    assert cone["family_label"] == "锥形"
    assert cone["collected"] is False

    methods = client.get("/api/brew/methods").json()["methods"]
    by = {m["key"]: m for m in methods}
    assert by["v60"]["owned"] is True
    assert by["volcano"]["owned"] is True
    assert by["kalita"]["owned"] is False
    assert by["v60"]["suggested"] is True
    assert by["kalita"]["suggested"] is False
    assert "我的 V60" in by["v60"]["gear_names"]

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "other@coffeebar.local", "password": "testpass1"},
    )
    assert client.get("/api/gear").json()["gear"] == []
    assert client.get(f"/api/gear/{cone['id']}").status_code == 404
    assert client.patch(f"/api/gear/{cone['id']}", json={"name": "偷"}).status_code == 404

    flat = client.post(
        "/api/gear",
        json={"name": "Kalita 185", "kind": "dripper", "family": "flat"},
    ).json()
    methods = client.get("/api/brew/methods").json()["methods"]
    by = {m["key"]: m for m in methods}
    assert by["kalita"]["owned"] is True
    assert by["kalita"]["suggested"] is True
    assert by["v60"]["owned"] is False
    assert flat["id"] != cone["id"]


def test_no_gear_means_methods_unmarked(client):
    methods = client.get("/api/brew/methods").json()["methods"]
    assert {m["key"] for m in methods} >= {"v60", "kalita", "volcano"}
    assert all(m["owned"] is None for m in methods)
    assert all(m["suggested"] is False for m in methods)
    client.post("/api/auth/logout")
    guest = client.get("/api/brew/methods")
    assert guest.status_code == 200
    assert all(m["owned"] is None for m in guest.json()["methods"])


def test_admin_collects_gear_into_catalog(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    item = client.post(
        "/api/gear",
        json={"name": "Origami Air", "kind": "dripper", "family": "cone", "note": "自己写的"},
    ).json()
    photo = client.post(f"/api/gear/{item['id']}/photos", files=_jpg()).json()
    name = photo["path"].split("/")[-1]
    assert (db.PHOTO_DIR / name).exists()

    assert client.get("/api/admin/gear/queue").status_code == 403

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    queue = client.get("/api/admin/gear/queue").json()
    assert any(g["id"] == item["id"] for g in queue["queue"])

    collected = client.post(
        f"/api/admin/gear/{item['id']}/collect",
        json={"brew_method": "v60", "note": "细水螺旋，别冲到滤纸"},
    ).json()
    cat = collected["catalog"]
    assert cat["brew_method"] == "v60"
    assert cat["note"] == "细水螺旋，别冲到滤纸"
    assert cat["photos"]
    catalog_name = cat["photos"][0]["path"].split("/")[-1]
    assert catalog_name != name
    assert (db.PHOTO_DIR / catalog_name).exists()

    empty = client.get("/api/admin/gear/queue").json()["queue"]
    assert all(g["id"] != item["id"] for g in empty)

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "third@coffeebar.local", "password": "testpass1"},
    )
    claimed = client.post(f"/api/gear/from-catalog/{cat['id']}").json()
    assert claimed["catalog_id"] == cat["id"]
    assert claimed["name"] == "Origami Air"
    methods = client.get("/api/brew/methods").json()["methods"]
    v60 = next(m for m in methods if m["key"] == "v60")
    assert v60["owned"] is True
    assert "细水螺旋，别冲到滤纸" in v60["tips"]
    assert client.post(f"/api/gear/from-catalog/{cat['id']}").status_code == 409


def test_explicit_brew_method_beats_family(client):
    client.post(
        "/api/gear",
        json={"name": "锥形但指定 Kalita", "kind": "dripper", "family": "cone", "brew_method": "kalita"},
    )
    methods = {m["key"]: m for m in client.get("/api/brew/methods").json()["methods"]}
    assert methods["kalita"]["owned"] is True
    assert methods["v60"]["owned"] is False


def test_delete_account_wipes_gear_keeps_catalog(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    item = client.post("/api/gear", json={"name": "要注销的壶", "kind": "kettle", "family": "gooseneck"}).json()
    photo = client.post(f"/api/gear/{item['id']}/photos", files=_jpg()).json()
    user_name = photo["path"].split("/")[-1]

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    cat = client.post(f"/api/admin/gear/{item['id']}/collect", json={}).json()["catalog"]
    cat_name = cat["photos"][0]["path"].split("/")[-1]

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"email": "test@coffeebar.local", "password": "testpass1"},
    )
    assert (
        client.post(
            "/api/auth/delete",
            json={"email": "test@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 200
    )
    assert not (db.PHOTO_DIR / user_name).exists()
    assert (db.PHOTO_DIR / cat_name).exists()

    client.post(
        "/api/auth/login",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    catalog = client.get("/api/admin/gear/queue").json()["catalog"]
    assert any(c["id"] == cat["id"] for c in catalog)


def test_ordinary_user_cannot_collect(client):
    item = client.post("/api/gear", json={"name": "自己的称", "kind": "scale"}).json()
    assert client.post(f"/api/admin/gear/{item['id']}/collect", json={}).status_code == 403
    assert client.get("/api/admin/gear/queue").status_code == 403
