"""照片：转码、缩略图、豆盘优先；以及开封只记日子不动克数。"""

import io

import pytest
from PIL import Image

from app import db, photos, store


def png_bytes(size=(1200, 900), color=(120, 80, 50)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def make_bean(client, **kw):
    payload = {"name": "测试豆", "nominal_g": 200, "price": 100.0, **kw}
    return client.post("/api/beans", json=payload).json()


# ── 照片 ────────────────────────────────────────────────────


def test_upload_converts_to_jpeg_and_makes_thumb(client):
    bean = make_bean(client)
    r = client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("bag.png", png_bytes(), "image/png")},
        data={"kind": "pack"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "pack"
    assert body["path"].endswith(".jpg"), "一律转成 JPEG，浏览器都认"

    name = body["path"].split("/")[-1]
    assert (db.PHOTO_DIR / name).exists()
    assert (db.PHOTO_DIR / f"t_{name}").exists(), "缩略图跟着生成"

    with Image.open(db.PHOTO_DIR / name) as im:
        assert max(im.size) <= photos.MAX_EDGE, "长边压到 1600 以内"
    with Image.open(db.PHOTO_DIR / f"t_{name}") as im:
        assert max(im.size) <= photos.THUMB_EDGE


def test_photo_is_served(client):
    bean = make_bean(client)
    p = client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("bag.png", png_bytes(), "image/png")},
    ).json()
    assert client.get(p["url"]).status_code == 200
    assert client.get(p["thumb"]).status_code == 200


def test_bean_detail_carries_photos(client):
    bean = make_bean(client)
    client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("a.png", png_bytes(), "image/png")},
        data={"kind": "pack"},
    )
    detail = client.get(f"/api/beans/{bean['id']}").json()
    assert len(detail["photos"]) == 1
    assert detail["photos"][0]["kind"] == "pack"


def test_library_cover_prefers_tray(client):
    """豆库缩略图优先豆盘，没有才用包装。"""
    bean = make_bean(client)
    for kind in ("pack", "tray"):
        client.post(
            f"/api/beans/{bean['id']}/photos",
            files={"file": (f"{kind}.png", png_bytes(), "image/png")},
            data={"kind": kind},
        )
    cover = client.get("/api/beans").json()["beans"][0]["cover"]
    assert cover["kind"] == "tray"


def test_library_cover_falls_back_to_pack(client):
    bean = make_bean(client)
    client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("pack.png", png_bytes(), "image/png")},
        data={"kind": "pack"},
    )
    assert client.get("/api/beans").json()["beans"][0]["cover"]["kind"] == "pack"


def test_no_photo_is_fine(client):
    """两种照片都可以缺，不挡建卡。"""
    make_bean(client)
    assert client.get("/api/beans").json()["beans"][0]["cover"] is None


def test_delete_photo_removes_files(client):
    bean = make_bean(client)
    p = client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("a.png", png_bytes(), "image/png")},
    ).json()
    name = p["path"].split("/")[-1]

    assert client.delete(f"/api/photos/{p['id']}").status_code == 200
    assert not (db.PHOTO_DIR / name).exists()
    assert not (db.PHOTO_DIR / f"t_{name}").exists()
    assert client.get(f"/api/beans/{bean['id']}").json()["photos"] == []


def test_reject_non_image(client):
    bean = make_bean(client)
    r = client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("notes.txt", b"just text", "text/plain")},
    )
    assert r.status_code == 400
    assert "不像图片" in r.json()["message"]


def test_reject_bad_kind(client):
    bean = make_bean(client)
    r = client.post(
        f"/api/beans/{bean['id']}/photos",
        files={"file": ("a.png", png_bytes(), "image/png")},
        data={"kind": "selfie"},
    )
    assert r.status_code == 400


def test_restock_photo(client):
    bean = make_bean(client)
    r = client.post(
        f"/api/beans/{bean['id']}/restock-photos",
        files={"file": ("shelf.png", png_bytes(), "image/png")},
        data={"note": "货架上还有两袋"},
    )
    assert r.status_code == 201

    client.post("/api/brews", json={"lot_id": bean["lots"][0]["id"], "amount_g": 16})
    client.post(f"/api/lots/{bean['lots'][0]['id']}/adjust", json={"actual_g": 5})
    item = client.get("/api/restock").json()["items"][0]
    assert len(item["photos"]) == 1


# ── 开封 ────────────────────────────────────────────────────


def test_open_records_day_without_touching_grams(client):
    """开封只记日子——撕开袋子没让豆子变少。"""
    bean = make_bean(client, nominal_g=454)
    lot = bean["lots"][0]
    assert lot["opened_on"] is None

    before = client.get(f"/api/beans/{bean['id']}").json()["balance_g"]
    r = client.post(f"/api/lots/{lot['id']}/open")
    assert r.status_code == 200
    assert r.json()["opened_on"] == db.now()[:10]
    assert client.get(f"/api/beans/{bean['id']}").json()["balance_g"] == pytest.approx(before)


def test_cannot_open_twice(client):
    bean = make_bean(client)
    lot = bean["lots"][0]["id"]
    client.post(f"/api/lots/{lot}/open")
    r = client.post(f"/api/lots/{lot}/open")
    assert r.status_code == 409
    assert "就开过了" in r.json()["message"]


def test_cannot_open_closed_lot(client):
    bean = make_bean(client)
    lot = bean["lots"][0]["id"]
    client.post(f"/api/lots/{lot}/close")
    assert client.post(f"/api/lots/{lot}/open").status_code == 409


def test_measure_only_after_opening(conn):
    """开封后补实称，改的是这袋原本有多少。"""
    bean_id = store.create_bean(conn, {"name": "巴西"})
    lot_id = store.add_lot(conn, bean_id, {"nominal_g": 454, "price": 90.0})
    store.open_lot(conn, lot_id)
    store.set_measured(conn, lot_id, 449)
    lot = store.get_lot(conn, lot_id)
    assert lot["usable_g"] == 449
    assert lot["balance_g"] == 449


# ── 豆种 ────────────────────────────────────────────────────


def test_varietal_round_trip(client):
    bean = make_bean(client, name="巴西 南米纳斯", varietal="黄波旁 Bourbon Amarelo")
    assert bean["varietal"] == "黄波旁 Bourbon Amarelo"
    assert client.get("/api/beans").json()["beans"][0]["varietal"] == "黄波旁 Bourbon Amarelo"

    client.patch(f"/api/beans/{bean['id']}", json={"varietal": "黄波旁"})
    assert client.get(f"/api/beans/{bean['id']}").json()["varietal"] == "黄波旁"


def add_photo(client, bean_id, kind):
    return client.post(
        f"/api/beans/{bean_id}/photos",
        files={"file": (f"{kind}.png", png_bytes(), "image/png")},
        data={"kind": kind},
    )


def test_card_photo_is_kept_but_not_used_as_cover(client):
    """豆卡要能存，但缩略图不该选它——缩下去只剩一片字。"""
    bean = make_bean(client)
    add_photo(client, bean["id"], "card")

    assert [p["kind"] for p in client.get(f"/api/beans/{bean['id']}").json()["photos"]] == ["card"]
    assert client.get("/api/beans").json()["beans"][0]["cover"]["kind"] == "card", \
        "只有豆卡时也得有图可看"

    add_photo(client, bean["id"], "pack")
    assert client.get("/api/beans").json()["beans"][0]["cover"]["kind"] == "pack"


def test_cover_skips_card_even_if_newest(client):
    """豆卡是最后传的也不该顶掉豆盘。"""
    bean = make_bean(client)
    for kind in ("tray", "card"):
        add_photo(client, bean["id"], kind)
    assert client.get("/api/beans").json()["beans"][0]["cover"]["kind"] == "tray"


def test_full_bean_card_round_trip(client):
    """店家豆卡上有的，系统都得能存下：处理厂、海拔、推荐冲法。"""
    bean = client.post("/api/beans", json={
        "name": "MATYAZO CWS 黑莓可可",
        "origin": "卢旺达 恩戈罗雷罗 Ngororero",
        "varietal": "红波旁 Red Bourbon",
        "producer": "Matyazo CWS 处理厂",
        "altitude": "1500-2200m",
        "process": "水洗",
        "roast": "中烘",
        "water_temp": 88,
        "brew_method": "volcano",
        "brew_dose_g": 15,
        "brew_ratio": 14,
        "brew_note": "KONO 法兰绒 · 富士 #7 · TDS 10-15 · 2'15\"",
        "tags": ["黑莓", "丁香", "阿克苏苹果", "太妃糖"],
        "nominal_g": 200,
    }).json()

    d = client.get(f"/api/beans/{bean['id']}").json()
    assert d["producer"] == "Matyazo CWS 处理厂"
    assert d["altitude"] == "1500-2200m"
    assert d["water_temp"] == 88
    assert d["brew"] == {
        "method": "volcano", "dose_g": 15, "ratio": 14,
        "note": "KONO 法兰绒 · 富士 #7 · TDS 10-15 · 2'15\"",
    }, "豆卡默认直接带上店家那套，不用每次重填"


def test_brew_note_survives_default_update(client):
    """改粉量比例不该把店家推荐抹掉。"""
    bean = client.post("/api/beans", json={
        "name": "卢旺达", "nominal_g": 200, "brew_note": "KONO 法兰绒",
    }).json()
    client.post(f"/api/beans/{bean['id']}/brew-default",
                json={"method": "v60", "dose_g": 18, "ratio": 16})
    d = client.get(f"/api/beans/{bean['id']}").json()
    assert d["brew"]["dose_g"] == 18
    assert d["brew"]["note"] == "KONO 法兰绒"


def test_card_only_bean_is_pending_not_history(client):
    """只建豆卡没入袋：跟着在库出并标待入袋，别掉进历史。"""
    client.post("/api/beans", json={"name": "只有豆卡"})

    stock = client.get("/api/beans?scope=stock").json()["beans"]
    assert [b["name"] for b in stock] == ["只有豆卡"]
    assert stock[0]["pending"] is True
    assert stock[0]["in_stock"] is False

    assert client.get("/api/beans?scope=history").json()["beans"] == [], "一袋都没有过，不算喝完"


def test_pending_bean_is_not_a_restock_item(client):
    """豆子在手上，缺的是称重录入，不是缺货。"""
    client.post("/api/beans", json={"name": "只有豆卡"})
    assert client.get("/api/restock").json()["items"] == []


def test_bean_leaves_pending_once_bagged(client):
    bean = client.post("/api/beans", json={"name": "只有豆卡"}).json()
    assert bean["pending"] is True

    client.post(f"/api/beans/{bean['id']}/lots", json={"nominal_g": 200, "price": 100})
    after = client.get(f"/api/beans/{bean['id']}").json()
    assert after["pending"] is False
    assert after["in_stock"] is True


def test_finished_bean_still_lands_in_history(client):
    """真喝完的（曾有袋、全关了）还得是历史，别被 pending 改坏。"""
    bean = make_bean(client)
    lot = client.get(f"/api/beans/{bean['id']}").json()["lots"][0]
    client.post(f"/api/lots/{lot['id']}/close", json={"note": "喝完了"})

    d = client.get(f"/api/beans/{bean['id']}").json()
    assert d["pending"] is False, "有过袋子就不是待入袋"
    assert d["in_stock"] is False
    assert [b["name"] for b in client.get("/api/beans?scope=history").json()["beans"]] == [d["name"]]
    assert client.get("/api/beans?scope=stock").json()["beans"] == []


def test_migration_adds_varietal_to_old_db(tmp_path, monkeypatch):
    """老库没有 varietal 列，启动时要自动补上。"""
    import importlib

    monkeypatch.setenv("COFFEEBAR_DATA", str(tmp_path))
    from app import db as db_mod

    importlib.reload(db_mod)

    conn = db_mod.connect()
    conn.execute(
        """CREATE TABLE bean (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
           origin TEXT, process TEXT, roast TEXT, water_temp INTEGER, note TEXT,
           created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    conn.execute(
        "INSERT INTO bean (name, created_at, updated_at) VALUES ('老豆', '2026-01-01', '2026-01-01')"
    )
    assert "varietal" not in {r[1] for r in conn.execute("PRAGMA table_info(bean)")}

    db_mod.init_db(conn)

    assert "varietal" in {r[1] for r in conn.execute("PRAGMA table_info(bean)")}
    assert conn.execute("SELECT name FROM bean").fetchone()[0] == "老豆", "老数据还在"
    conn.close()


def test_migration_relaxes_photo_kind_on_old_db(tmp_path, monkeypatch):
    """老库的 CHECK 只认 pack/tray，SQLite 改不了 CHECK，得重建表且不丢照片。"""
    import importlib

    monkeypatch.setenv("COFFEEBAR_DATA", str(tmp_path))
    from app import db as db_mod

    importlib.reload(db_mod)

    conn = db_mod.connect()
    db_mod.init_db(conn)
    # 退回老结构：带旧 CHECK，并塞一张老照片
    conn.executescript(
        """DROP TABLE bean_photo;
           CREATE TABLE bean_photo (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             bean_id INTEGER NOT NULL REFERENCES bean(id) ON DELETE CASCADE,
             kind TEXT NOT NULL CHECK (kind IN ('pack', 'tray')),
             path TEXT NOT NULL,
             created_at TEXT NOT NULL);"""
    )
    bean_id = store.create_bean(conn, {"name": "老豆"})
    conn.execute(
        "INSERT INTO bean_photo (bean_id, kind, path, created_at)"
        " VALUES (?, 'pack', 'data/photos/old.jpg', '2026-01-01')",
        (bean_id,),
    )
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO bean_photo (bean_id, kind, path, created_at)"
            " VALUES (?, 'card', 'x.jpg', '2026-01-01')",
            (bean_id,),
        )

    db_mod.init_db(conn)

    rows = conn.execute("SELECT bean_id, kind, path FROM bean_photo").fetchall()
    assert [tuple(r) for r in rows] == [(bean_id, "pack", "data/photos/old.jpg")], "老照片没丢"
    conn.execute(
        "INSERT INTO bean_photo (bean_id, kind, path, created_at)"
        " VALUES (?, 'card', 'data/photos/card.jpg', '2026-01-02')",
        (bean_id,),
    )
    assert conn.execute("SELECT COUNT(*) FROM bean_photo").fetchone()[0] == 2
    # 重建后自增主键和级联删除都得还在
    assert conn.execute("SELECT MAX(id) FROM bean_photo").fetchone()[0] == 2
    conn.execute("DELETE FROM bean WHERE id = ?", (bean_id,))
    assert conn.execute("SELECT COUNT(*) FROM bean_photo").fetchone()[0] == 0, "级联删除还在"
    conn.close()


def test_migration_is_idempotent(tmp_path, monkeypatch):
    """反复启动不该反复重建表。"""
    import importlib

    monkeypatch.setenv("COFFEEBAR_DATA", str(tmp_path))
    from app import db as db_mod

    importlib.reload(db_mod)
    conn = db_mod.connect()
    for _ in range(3):
        db_mod.init_db(conn)
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '_old_%'"
    ).fetchone()[0] == 0, "没留下临时表"
    conn.close()
