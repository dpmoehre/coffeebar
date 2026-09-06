"""账号与归属：A 看不到 B 的豆、酒、钱。"""

import hashlib
import secrets
import tempfile

from app import auth, photos, spirits, store


def test_register_and_me(client):
    me = client.get("/api/me").json()
    assert me["email"] == "test@coffeebar.local"
    assert me["email_verified"] is True


def test_empty_register_gets_yirgacheffe(conn, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_STARTER_BEAN", "1")
    out = auth.register(conn, "new@coffeebar.local", "testpass1")
    beans = store.list_beans(conn, owner_id=out["id"])
    assert [b["name"] for b in beans] == ["耶加雪菲"]
    assert beans[0]["origin"] == "埃塞俄比亚 耶加雪菲"
    assert beans[0]["balance_g"] == 100
    shots = photos.list_bean_photos(conn, beans[0]["id"])
    assert shots and shots[0]["kind"] == "pack"
    assert auth.is_stock_account(conn, out["id"]) is False


def test_take_orphans_skips_starter(conn, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_STARTER_BEAN", "1")
    store.create_bean(conn, {"name": "老豆"})
    out = auth.register(conn, "owner@coffeebar.local", "testpass1", claim="take")
    names = [b["name"] for b in store.list_beans(conn, owner_id=out["id"])]
    assert names == ["老豆"]
    assert auth.is_stock_account(conn, out["id"]) is True


def test_leave_orphans_gets_starter(conn, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_STARTER_BEAN", "1")
    store.create_bean(conn, {"name": "老豆"})
    out = auth.register(conn, "guest@coffeebar.local", "testpass1", claim="leave")
    names = [b["name"] for b in store.list_beans(conn, owner_id=out["id"])]
    assert names == ["耶加雪菲"]
    assert conn.execute("SELECT owner_id, name FROM bean WHERE name = '老豆'").fetchone()["owner_id"] is None
    assert auth.is_stock_account(conn, out["id"]) is False


def test_starter_account_can_delete_without_export(conn, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_STARTER_BEAN", "1")
    out = auth.register(conn, "seed@coffeebar.local", "testpass1")
    auth.delete_account(conn, out, "seed@coffeebar.local", "testpass1")
    assert conn.execute("SELECT id FROM account WHERE email = ?", ("seed@coffeebar.local",)).fetchone() is None
    assert store.list_beans(conn, owner_id=out["id"]) == []


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
    try:
        auth.register(conn, "owner@coffeebar.local", "testpass1")
        raise AssertionError("应该先问要不要接手")
    except auth.OrphansPending as exc:
        assert exc.counts["beans"] == 1
        assert exc.counts["bottles"] == 1
    assert conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0
    assert conn.execute("SELECT owner_id FROM bean").fetchone()["owner_id"] is None

    out = auth.register(conn, "owner@coffeebar.local", "testpass1", claim="take")
    assert out["claimed"] is True
    assert store.list_beans(conn, owner_id=out["id"])[0]["name"] == "老豆"
    assert spirits.list_spirits(conn, owner_id=out["id"])[0]["name"] == "老酒"
    assert store.list_people(conn, owner_id=out["id"])[0]["name"] == "戚浩辰"

    other = auth.register(conn, "other@coffeebar.local", "testpass1")
    assert other["claimed"] is False
    assert store.list_beans(conn, owner_id=other["id"]) == []


def test_leave_orphans_then_claim(conn):
    store.create_bean(conn, {"name": "老豆"})
    first = auth.register(conn, "owner@coffeebar.local", "testpass1", claim="leave")
    assert first["claimed"] is False
    assert conn.execute("SELECT owner_id FROM bean").fetchone()["owner_id"] is None
    try:
        auth.register(conn, "guest@coffeebar.local", "testpass1", claim="take")
        raise AssertionError("第二人不能接手")
    except Exception as exc:
        from fastapi import HTTPException

        assert isinstance(exc, HTTPException) and exc.status_code == 403
    auth.claim_now(conn, first)
    assert store.list_beans(conn, owner_id=first["id"])[0]["name"] == "老豆"


def test_password_is_argon2(conn):
    out = auth.register(conn, "hash@coffeebar.local", "testpass1")
    row = conn.execute("SELECT password_hash FROM account WHERE id = ?", (out["id"],)).fetchone()
    assert row["password_hash"].startswith("$argon2")


def test_login_upgrades_pbkdf2(conn):
    email = "old@coffeebar.local"
    password = "testpass1"
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    stored = f"pbkdf2_sha256$200000${salt}${dk.hex()}"
    conn.execute(
        "INSERT INTO account (email, password_hash, email_verified, created_at) VALUES (?, ?, 1, ?)",
        (email, stored, "2026-01-01 00:00:00"),
    )
    auth.login(conn, email, password)
    row = conn.execute("SELECT password_hash FROM account WHERE email = ?", (email,)).fetchone()
    assert row["password_hash"].startswith("$argon2")
    assert auth.check_password(password, row["password_hash"])


def test_forgot_and_reset(client):
    r = client.post("/api/auth/forgot", json={"email": "test@coffeebar.local"})
    assert r.status_code == 200
    url = r.json()["reset_url"]
    token = url.split("reset=", 1)[1]
    assert client.post("/api/auth/reset", json={"token": token, "password": "newpass12"}).status_code == 200
    assert client.get("/api/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "test@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "test@coffeebar.local", "password": "newpass12"},
        ).status_code
        == 200
    )
    reused = client.post("/api/auth/reset", json={"token": token, "password": "another99"})
    assert reused.status_code == 400


def test_forgot_unknown_email(client):
    r = client.post("/api/auth/forgot", json={"email": "nobody@coffeebar.local"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_verify_email(client, monkeypatch):
    monkeypatch.setattr("app.mail.configured", lambda: True)
    monkeypatch.setattr("app.mail.send", lambda *a, **k: False)
    client.post("/api/auth/logout")
    r = client.post(
        "/api/auth/register",
        json={"email": "v@coffeebar.local", "password": "testpass1"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email_verified"] is False
    token = body["verify_url"].split("verify=", 1)[1]
    v = client.post("/api/auth/verify", json={"token": token})
    assert v.status_code == 200
    assert v.json()["email_verified"] is True
    assert client.get("/api/me").json()["email_verified"] is True
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 400


def test_login_rate_limit(monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    from app import db as db_mod
    from app import main as main_mod
    from app import ratelimit

    tmp = tempfile.mkdtemp(prefix="coffeebar-rl-")
    monkeypatch.setenv("COFFEEBAR_DATA", tmp)
    monkeypatch.setenv("COFFEEBAR_RATE_LIMIT", "1")
    importlib.reload(db_mod)
    ratelimit._hits.clear()
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        assert (
            c.post(
                "/api/auth/register",
                json={"email": "rl@coffeebar.local", "password": "testpass1"},
            ).status_code
            == 201
        )
        for _ in range(4):
            ok = c.post(
                "/api/auth/login",
                json={"email": "rl@coffeebar.local", "password": "testpass1"},
            )
            assert ok.status_code == 200
        for i in range(5):
            r = c.post(
                "/api/auth/login",
                json={"email": "rl@coffeebar.local", "password": "wrongwrong"},
                headers={"X-Source": "web"},
            )
            assert r.status_code == 401, i
        for i in range(5):
            mcp = c.post(
                "/api/auth/login",
                json={"email": "rl@coffeebar.local", "password": "wrongwrong"},
                headers={"X-Source": "mcp"},
            )
            assert mcp.status_code == 401, i
        blocked = c.post(
            "/api/auth/login",
            json={"email": "rl@coffeebar.local", "password": "wrongwrong"},
            headers={"X-Source": "web"},
        )
        assert blocked.status_code == 429
        assert "5 次" in (blocked.json().get("detail") or "")


def test_change_password_keeps_this_session(client):
    bad = client.post("/api/auth/password", json={"old": "nopexxxx", "new": "newpass12"})
    assert bad.status_code == 401
    short = client.post("/api/auth/password", json={"old": "testpass1", "new": "short"})
    assert short.status_code == 400
    same = client.post("/api/auth/password", json={"old": "testpass1", "new": "testpass1"})
    assert same.status_code == 400
    ok = client.post("/api/auth/password", json={"old": "testpass1", "new": "newpass12"})
    assert ok.status_code == 200
    assert client.get("/api/me").status_code == 200
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "test@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "test@coffeebar.local", "password": "newpass12"},
        ).status_code
        == 200
    )


def test_change_password_kicks_other_device(client):
    from app import auth, db as db_mod

    conn = db_mod.connect()
    row = conn.execute("SELECT id FROM account WHERE email = ?", ("test@coffeebar.local",)).fetchone()
    other = auth.issue_session(conn, row["id"])
    conn.close()

    assert client.post("/api/auth/password", json={"old": "testpass1", "new": "newpass12"}).status_code == 200
    conn = db_mod.connect()
    assert auth.account_from_token(conn, other) is None
    conn.close()
    assert client.get("/api/me").status_code == 200


def test_cookie_secure_when_forced(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_COOKIE_SECURE", "1")
    r = client.post(
        "/api/auth/login",
        json={"email": "test@coffeebar.local", "password": "testpass1"},
    )
    assert r.status_code == 200
    assert "secure" in r.headers.get("set-cookie", "").lower()


def _point_person_fk_at_old(conn):
    """复现小主机：外键开着时重建 person，流水会指到已经删掉的 _old_person。"""
    from app import db as db_mod

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("ALTER TABLE person RENAME TO _old_person")
    ddl = next(
        s
        for s in db_mod.SCHEMA.read_text(encoding="utf-8").split(";")
        if "CREATE TABLE IF NOT EXISTS person" in s
    )
    conn.executescript(ddl + ";")
    old = [r[1] for r in conn.execute("PRAGMA table_info(_old_person)")]
    keep = [c for c in (r[1] for r in conn.execute("PRAGMA table_info(person)")) if c in old]
    cols = ", ".join(keep)
    conn.execute(f"INSERT INTO person ({cols}) SELECT {cols} FROM _old_person")
    conn.execute("DROP TABLE _old_person")


def test_init_repairs_old_person_fk(conn):
    from app import db as db_mod

    _point_person_fk_at_old(conn)
    broken = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'consumption_event'"
    ).fetchone()["sql"]
    assert "_old_person" in broken
    db_mod.init_db(conn)
    fixed = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'consumption_event'"
    ).fetchone()["sql"]
    assert "_old_person" not in fixed
    conn.execute("UPDATE consumption_event SET person_id = NULL")


def test_delete_account_with_broken_person_fk(client):
    from app import db as db_mod

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "oldp@coffeebar.local", "password": "testpass1"},
    )
    client.post("/api/people", json={"name": "路人"})
    side = db_mod.connect()
    _point_person_fk_at_old(side)
    side.close()
    r = client.post(
        "/api/auth/delete",
        json={"email": "oldp@coffeebar.local", "password": "testpass1"},
    )
    assert r.status_code == 200, r.text


def test_delete_empty_account(client):
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "empty@coffeebar.local", "password": "testpass1"},
    )
    assert (
        client.post(
            "/api/auth/delete",
            json={"email": "empty@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 200
    )
    assert client.get("/api/me").status_code == 401


def test_delete_account_wipes_only_self(client):
    from app import db
    from tests.test_photos import png_bytes

    client.post("/api/beans", json={"name": "A 的豆", "nominal_g": 200})
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "gone@coffeebar.local", "password": "testpass1"},
    )
    b_bean = client.post("/api/beans", json={"name": "B 的豆", "nominal_g": 100, "price": 40}).json()
    photo = client.post(
        f"/api/beans/{b_bean['id']}/photos",
        files={"file": ("bag.png", png_bytes(), "image/png")},
        data={"kind": "pack"},
    ).json()
    name = photo["path"].split("/")[-1]
    assert (db.PHOTO_DIR / name).exists()
    client.post(
        "/api/spirits",
        json={"name": "B 的酒", "kind": "威士忌", "abv": 40, "nominal_ml": 700, "price": 99},
    )
    client.post("/api/people", json={"name": "路人"})

    assert (
        client.post("/api/auth/delete", json={"email": "wrong@x.com", "password": "testpass1"}).status_code
        == 400
    )
    assert (
        client.post(
            "/api/auth/delete", json={"email": "gone@coffeebar.local", "password": "nopexxxx"}
        ).status_code
        == 401
    )
    denied = client.post(
        "/api/auth/delete", json={"email": "gone@coffeebar.local", "password": "testpass1"}
    )
    assert denied.status_code == 400
    pack = client.get("/api/ops/backup")
    assert pack.status_code == 200
    token = pack.headers.get("x-export-token")
    assert token
    assert (
        client.post(
            "/api/auth/delete",
            json={
                "email": "gone@coffeebar.local",
                "password": "testpass1",
                "export_token": token,
            },
        ).status_code
        == 200
    )
    assert client.get("/api/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "gone@coffeebar.local", "password": "testpass1"},
        ).status_code
        == 401
    )
    assert not (db.PHOTO_DIR / name).exists()

    client.post(
        "/api/auth/login",
        json={"email": "test@coffeebar.local", "password": "testpass1"},
    )
    names = [b["name"] for b in client.get("/api/beans").json()["beans"]]
    assert "A 的豆" in names
    assert "B 的豆" not in names

    again = client.post(
        "/api/auth/register",
        json={"email": "gone@coffeebar.local", "password": "testpass1"},
    )
    assert again.status_code == 201
    assert client.get("/api/beans").json()["beans"] == []


def test_upload_rate_limit(monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    from app import db as db_mod
    from app import main as main_mod
    from app import ratelimit
    from tests.test_photos import png_bytes

    tmp = tempfile.mkdtemp(prefix="coffeebar-up-")
    monkeypatch.setenv("COFFEEBAR_DATA", tmp)
    monkeypatch.setenv("COFFEEBAR_RATE_LIMIT", "1")
    importlib.reload(db_mod)
    ratelimit._hits.clear()
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        assert (
            c.post(
                "/api/auth/register",
                json={"email": "up@coffeebar.local", "password": "testpass1"},
            ).status_code
            == 201
        )
        bean = c.post("/api/beans", json={"name": "限流豆", "nominal_g": 50}).json()
        tiny = png_bytes(size=(32, 32))
        for i in range(20):
            r = c.post(
                f"/api/beans/{bean['id']}/photos",
                files={"file": (f"{i}.png", tiny, "image/png")},
                data={"kind": "pack"},
            )
            assert r.status_code == 201, i
        blocked = c.post(
            f"/api/beans/{bean['id']}/photos",
            files={"file": ("last.png", tiny, "image/png")},
            data={"kind": "pack"},
        )
        assert blocked.status_code == 429


def test_auth_config_invite_flag(client, monkeypatch):
    assert client.get("/api/auth/config").json()["invite_required"] is False
    monkeypatch.setenv("COFFEEBAR_INVITE_CODE", "only-us")
    assert client.get("/api/auth/config").json()["invite_required"] is True


def test_register_needs_invite_when_set(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_INVITE_CODE", "only-us")
    client.post("/api/auth/logout")
    denied = client.post(
        "/api/auth/register",
        json={"email": "stranger@coffeebar.local", "password": "testpass1"},
    )
    assert denied.status_code == 403
    ok = client.post(
        "/api/auth/register",
        json={
            "email": "friend@coffeebar.local",
            "password": "testpass1",
            "invite": "only-us",
        },
    )
    assert ok.status_code == 201
    assert ok.json()["email"] == "friend@coffeebar.local"


def test_restore_rejects_bad_key(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_RESTORE_KEY", "restore-me")
    r = client.post(
        "/api/ops/restore",
        files={"file": ("x.zip", b"not-a-zip", "application/zip")},
        headers={"X-Restore-Key": "wrong"},
    )
    assert r.status_code == 403
