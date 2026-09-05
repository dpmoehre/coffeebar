"""日历按凌晨 4 点分日；出表带汇总和明细；撤回不进日历点数。"""

import io
import zipfile

from app import db, ledger, spirits, store


def _owner(conn):
    cur = conn.execute(
        "INSERT INTO account (email, password_hash, created_at) VALUES ('ledger@c.local', 'x', ?)",
        (db.now(),),
    )
    return int(cur.lastrowid)


def _bean(conn, owner_id, name="西达摩"):
    bean_id = store.create_bean(conn, {"name": name, "owner_id": owner_id})
    lot_id = store.add_lot(conn, bean_id, {"nominal_g": 200, "price": 100})
    return bean_id, lot_id


def test_business_day_cuts_at_4am():
    assert db.business_day("2026-09-06 03:59:00") == "2026-09-05"
    assert db.business_day("2026-09-06 04:00:00") == "2026-09-06"


def test_calendar_marks_coffee_and_drink(conn):
    owner = _owner(conn)
    _, lot = _bean(conn, owner)
    store.record_brew(
        conn,
        {"lot_id": lot, "amount_g": 16, "person": "戚浩辰", "owner_id": owner, "at": "2026-09-05 10:00:00"},
    )
    store.record_brew(
        conn,
        {"lot_id": lot, "amount_g": 15, "person": "戚浩辰", "owner_id": owner, "at": "2026-09-06 02:00:00"},
    )
    sid = spirits.create_spirit(conn, {"name": "格兰杰", "abv": 43, "kind": "威士忌", "owner_id": owner})
    blot = spirits.add_lot(conn, sid, {"nominal_ml": 700, "price": 399})
    spirits.record_drink(
        conn,
        {"lot_id": blot, "amount_ml": 30, "person": "丁瀚舟", "owner_id": owner, "at": "2026-09-05 20:00:00"},
    )

    month = ledger.month(conn, 2026, 9, owner)
    by_day = {d["date"]: d for d in month["days"]}
    assert by_day["2026-09-05"]["coffee"] == 2  # 10:00 和次日 02:00
    assert by_day["2026-09-05"]["drink"] == 1
    assert "2026-09-06" not in by_day

    detail = ledger.day(conn, "2026-09-05", owner)
    names = {e["name"] for e in detail["events"]}
    assert "西达摩" in names
    assert "格兰杰" in names


def test_voided_not_counted_on_month_but_listed(conn):
    owner = _owner(conn)
    _, lot = _bean(conn, owner)
    keep = store.record_brew(conn, {"lot_id": lot, "amount_g": 16, "owner_id": owner, "at": "2026-09-05 11:00:00"})
    drop = store.record_brew(conn, {"lot_id": lot, "amount_g": 16, "owner_id": owner, "at": "2026-09-05 12:00:00"})
    store.void_consumption(conn, drop["id"])
    month = ledger.month(conn, 2026, 9, owner)
    assert month["days"][0]["coffee"] == 1
    events = ledger.day(conn, "2026-09-05", owner)["events"]
    assert len(events) == 2
    assert sum(1 for e in events if e["voided"]) == 1
    assert keep["id"] in {e["id"] for e in events}


def test_export_zip_has_sheets_and_bom(conn):
    owner = _owner(conn)
    _, lot = _bean(conn, owner)
    store.record_brew(
        conn,
        {"lot_id": lot, "amount_g": 16, "person": "戚浩辰", "owner_id": owner, "at": "2026-09-05 10:00:00"},
    )
    raw = ledger.export_zip(conn, owner, "all")
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = set(zf.namelist())
    assert "统计汇总.csv" in names
    assert "消耗明细.csv" in names
    assert "豆库.csv" in names
    detail = zf.read("消耗明细.csv")
    assert detail.startswith(b"\xef\xbb\xbf")
    text = detail.decode("utf-8-sig")
    assert "西达摩" in text
    assert "戚浩辰" in text
    assert "关袋偏差" in zf.read("豆子批次.csv").decode("utf-8-sig")


def test_calendar_and_export_http(client):
    bean = client.post(
        "/api/beans",
        json={"name": "日历豆", "nominal_g": 200, "price": 80},
    ).json()
    lot_id = bean["lots"][0]["id"]
    client.post("/api/brews", json={"lot_id": lot_id, "amount_g": 16, "person": "戚浩辰", "at": "2026-09-05 10:00:00"})
    month = client.get("/api/calendar?year=2026&month=9").json()
    assert any(d["date"] == "2026-09-05" and d["coffee"] >= 1 for d in month["days"])
    day = client.get("/api/calendar/day?date=2026-09-05").json()
    assert day["events"][0]["name"] == "日历豆"
    assert client.get("/api/calendar/day?date=不是日期").status_code == 400
    z = client.get("/api/export?period=all")
    assert z.status_code == 200
    assert z.headers["content-type"].startswith("application/zip")
    assert zipfile.is_zipfile(io.BytesIO(z.content))
    assert client.get("/api/export?period=decade").status_code == 400
    assert client.get("/api/calendar?year=2026&month=9&person_id=99999").status_code == 404
    people = client.get("/api/people").json()["people"]
    qh = next(p for p in people if p["name"] == "戚浩辰")
    filtered = client.get(f"/api/calendar?year=2026&month=9&person_id={qh['id']}").json()
    assert any(d["date"] == "2026-09-05" and d["coffee"] >= 1 for d in filtered["days"])


def test_calendar_hides_other_account(client):
    bean = client.post(
        "/api/beans",
        json={"name": "A的豆", "nominal_g": 200, "price": 80},
    ).json()
    client.post(
        "/api/brews",
        json={"lot_id": bean["lots"][0]["id"], "amount_g": 16, "at": "2026-09-05 10:00:00"},
    )
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "calnosy@coffeebar.local", "password": "testpass1"},
    )
    assert client.get("/api/calendar?year=2026&month=9").json()["days"] == []
    assert client.get("/api/calendar/day?date=2026-09-05").json()["events"] == []
