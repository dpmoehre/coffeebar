"""豆库「今天」条：业务日凌晨 4 点、撤回不上芯片、别人账号看不见。"""

from datetime import date, timedelta

from app import db, spirits, store, today


def _owner(conn):
    cur = conn.execute(
        "INSERT INTO account (email, password_hash, created_at) VALUES ('today@c.local', 'x', ?)",
        (db.now(),),
    )
    return int(cur.lastrowid)


def _bean(conn, owner_id, name="今天豆", **lot):
    bean_id = store.create_bean(conn, {"name": name, "owner_id": owner_id, "roast": "浅烘"})
    payload = {"nominal_g": 200, "price": 80, **lot}
    lot_id = store.add_lot(conn, bean_id, payload)
    return bean_id, lot_id


def day(n):
    return (date.today() - timedelta(days=n)).isoformat()


def test_today_3am_brew_counts_as_yesterday(conn):
    owner = _owner(conn)
    _, lot = _bean(conn, owner)
    store.record_brew(
        conn,
        {
            "lot_id": lot,
            "amount_g": 16,
            "person": "戚浩辰",
            "owner_id": owner,
            "at": "2026-09-06 03:00:00",
        },
    )
    morning = today.snapshot(conn, owner, day="2026-09-06")
    assert morning["people"] == []
    eve = today.snapshot(conn, owner, day="2026-09-05")
    assert len(eve["people"]) == 1
    assert eve["people"][0]["name"] == "戚浩辰"
    assert eve["people"][0]["coffee"] == 1


def test_today_voided_person_not_on_chips(conn):
    owner = _owner(conn)
    _, lot = _bean(conn, owner)
    keep = store.record_brew(
        conn,
        {
            "lot_id": lot,
            "amount_g": 16,
            "person": "丁瀚舟",
            "owner_id": owner,
            "at": "2026-09-06 10:00:00",
        },
    )
    drop = store.record_brew(
        conn,
        {
            "lot_id": lot,
            "amount_g": 16,
            "person": "戚浩辰",
            "owner_id": owner,
            "at": "2026-09-06 11:00:00",
        },
    )
    store.void_consumption(conn, drop["id"])
    bar = today.snapshot(conn, owner, day="2026-09-06")
    names = [p["name"] for p in bar["people"]]
    assert names == ["丁瀚舟"]
    assert bar["last_cup"]["bean_id"]
    assert bar["last_cup"]["person_name"] == "丁瀚舟"
    store.void_consumption(conn, keep["id"])
    empty = today.snapshot(conn, owner, day="2026-09-06")
    assert empty["people"] == []
    assert empty["last_cup"] is None


def test_today_hides_other_account(client):
    bean = client.post(
        "/api/beans",
        json={"name": "A的豆", "nominal_g": 200, "price": 80},
    ).json()
    client.post(
        "/api/brews",
        json={"lot_id": bean["lots"][0]["id"], "amount_g": 16, "person": "丁瀚舟"},
    )
    mine = client.get("/api/today").json()
    assert any(p["name"] == "丁瀚舟" for p in mine["people"])
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "todaynosy@coffeebar.local", "password": "testpass1"},
    )
    other = client.get("/api/today").json()
    assert other["people"] == []
    assert other["last_cup"] is None


def test_today_as_cup_zero_not_a_cup(conn):
    owner = _owner(conn)
    _, lot = _bean(conn, owner)
    store.record_brew(
        conn,
        {
            "lot_id": lot,
            "amount_g": 16,
            "person": "戚浩辰",
            "owner_id": owner,
            "as_cup": 0,
            "at": "2026-09-06 10:00:00",
        },
    )
    bar = today.snapshot(conn, owner, day="2026-09-06")
    assert bar["people"] == []
    assert bar["last_cup"] is None


def test_today_drink_shows_in_paren(conn):
    owner = _owner(conn)
    sid = spirits.create_spirit(
        conn, {"name": "格兰杰", "abv": 43, "kind": "威士忌", "owner_id": owner}
    )
    blot = spirits.add_lot(conn, sid, {"nominal_ml": 700, "price": 399})
    spirits.record_drink(
        conn,
        {
            "lot_id": blot,
            "amount_ml": 30,
            "person": "丁瀚舟",
            "owner_id": owner,
            "at": "2026-09-06 20:00:00",
        },
    )
    bar = today.snapshot(conn, owner, day="2026-09-06")
    assert bar["people"][0]["name"] == "丁瀚舟"
    assert bar["people"][0]["coffee"] == 0
    assert bar["people"][0]["drink"] == 1


def test_today_taste_and_last_cup_compare(conn):
    owner = _owner(conn)
    peak_id, peak_lot = _bean(conn, owner, name="正当时豆", roasted_on=day(12))
    stale_id, _ = _bean(conn, owner, name="老了豆", roasted_on=day(60))
    long_id, long_lot = _bean(conn, owner, name="开封久豆", roasted_on=day(8))
    store.open_lot(conn, long_lot, on=day(16))
    store.record_brew(
        conn,
        {
            "lot_id": peak_lot,
            "amount_g": 15,
            "person": "戚浩辰",
            "owner_id": owner,
            "brew_method": "v60",
            "brew_ratio": 16,
            "brew_total_s": 60,
            "at": "2026-09-06 09:00:00",
        },
    )
    bar = today.snapshot(conn, owner, day="2026-09-06")
    assert [b["id"] for b in bar["peak"]] == [peak_id]
    assert bar["stale"]["id"] == stale_id
    assert bar["opened_long"]["id"] == long_id
    cup = bar["last_cup"]
    assert cup["bean_id"] == peak_id
    assert cup["actual_s"] == 60
    assert cup["planned_s"]
    assert "细" in (cup["label"] or "")


def test_today_http_empty_keys(client):
    data = client.get("/api/today").json()
    assert data["people"] == []
    assert data["peak"] == []
    assert data["stale"] is None
    assert data["opened_long"] is None
    assert data["restock"]["n"] == 0
    assert data["last_cup"] is None
    assert data["day"]
