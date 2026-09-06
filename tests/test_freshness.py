"""烘焙日、赏味窗、杯测快照。"""

from datetime import date, timedelta

import pytest

from app import freshness, store


def today():
    return date.today()


def day(n):
    return (today() - timedelta(days=n)).isoformat()


def make_bean(conn, roast="浅烘", roasted_on=None):
    bean_id = store.create_bean(conn, {"name": "赏味测试", "roast": roast})
    lot_id = store.add_lot(conn, bean_id, {"nominal_g": 200, "roasted_on": roasted_on})
    return bean_id, lot_id


def test_window_bands():
    assert freshness.window("浅烘") == (10, 28, 56)
    assert freshness.window("中浅烘") == (10, 28, 56)
    assert freshness.window("中烘") == (7, 21, 42)
    assert freshness.window("中深烘") == (5, 18, 35)
    assert freshness.window("深烘") == (4, 14, 28)
    assert freshness.window("怪烘焙") == (7, 21, 42)


def test_light_roast_boundaries():
    roast = "浅烘"
    now = "2026-09-05"
    assert freshness.of("2026-08-27", roast, today=now)["phase"] == "resting"  # 第 9 天
    assert freshness.of("2026-08-27", roast, today=now)["days_after_roast"] == 9
    assert freshness.of("2026-08-26", roast, today=now)["phase"] == "peak"  # 第 10 天
    assert freshness.of("2026-08-08", roast, today=now)["phase"] == "fading"  # 第 28 天
    assert freshness.of("2026-07-11", roast, today=now)["phase"] == "stale"  # 第 56 天
    assert freshness.of(None, roast, today=now)["phase"] == "unknown"


def test_opened_long_over_14_days():
    now = "2026-09-05"
    assert freshness.of(None, "浅烘", opened_on="2026-08-21", today=now)["opened_long"] is True
    assert freshness.of(None, "浅烘", opened_on="2026-08-22", today=now)["opened_long"] is False
    assert freshness.of(None, "浅烘", opened_on=None, today=now)["opened_long"] is False


def test_old_lot_lists_without_roast_date(conn):
    bean_id, lot_id = make_bean(conn)
    lot = store.get_lot(conn, lot_id)
    assert lot["roasted_on"] is None
    assert lot["freshness"]["phase"] == "unknown"
    lots = store.list_lots(conn, bean_id)
    assert lots[0]["roasted_on"] is None


def test_write_roast_date_and_reject_future(conn):
    bean_id, lot_id = make_bean(conn, roasted_on="2026-08-01")
    assert store.get_lot(conn, lot_id)["roasted_on"] == "2026-08-01"
    before = conn.execute("SELECT COUNT(*) c FROM stock_event WHERE lot_id = ?", (lot_id,)).fetchone()["c"]
    store.set_lot_roasted_on(conn, lot_id, "2026-07-20")
    after = conn.execute("SELECT COUNT(*) c FROM stock_event WHERE lot_id = ?", (lot_id,)).fetchone()["c"]
    assert after == before
    assert store.get_lot(conn, lot_id)["roasted_on"] == "2026-07-20"
    with pytest.raises(store.Conflict, match="晚于今天"):
        store.add_lot(conn, bean_id, {"nominal_g": 200, "roasted_on": "2099-01-01"})
    with pytest.raises(store.Conflict, match="合法日期"):
        store.add_lot(conn, bean_id, {"nominal_g": 200, "roasted_on": "2026-13-40"})


def test_list_beans_carries_freshness(conn):
    bean_id, _ = make_bean(conn, roast="浅烘", roasted_on=day(12))
    hit = next(b for b in store.list_beans(conn) if b["id"] == bean_id)
    assert hit["freshness"]["days_after_roast"] == 12
    assert hit["freshness"]["phase"] == "peak"


def test_history_uses_last_closed_lot(conn):
    bean_id = store.create_bean(conn, {"name": "两袋", "roast": "浅烘"})
    first = store.add_lot(conn, bean_id, {"nominal_g": 200, "roasted_on": day(60)})
    second = store.add_lot(conn, bean_id, {"nominal_g": 200, "roasted_on": day(5)})
    store.close_lot(conn, first)
    store.close_lot(conn, second)
    bean = store.get_bean(conn, bean_id)
    assert bean["freshness"]["days_after_roast"] == 5
    assert bean["freshness"]["phase"] == "resting"


def test_score_snapshot_does_not_follow_lot(conn):
    bean_id, lot_id = make_bean(conn, roast="浅烘", roasted_on=day(12))
    store.add_score(conn, bean_id, {"overall": 8, "lot_id": lot_id})
    score = store.latest_score(conn, bean_id)
    assert score["days_after_roast"] == 12
    assert score["window_phase"] == "peak"
    assert score["roasted_on"] == day(12)
    store.set_lot_roasted_on(conn, lot_id, day(30))
    old = store.latest_score(conn, bean_id)
    assert old["days_after_roast"] == 12
    assert old["roasted_on"] == day(12)
    bean = store.get_bean(conn, bean_id)
    assert bean["freshness"]["days_after_roast"] == 30
    assert bean["freshness"]["phase"] == "fading"


def test_score_without_roast_leaves_phase_empty(conn):
    bean_id, lot_id = make_bean(conn)
    store.add_score(conn, bean_id, {"overall": 7, "lot_id": lot_id})
    score = store.latest_score(conn, bean_id)
    assert score["days_after_roast"] is None
    assert score["window_phase"] is None


def test_score_writes_roast_back_to_empty_lot(conn):
    bean_id, lot_id = make_bean(conn)
    store.add_score(conn, bean_id, {"overall": 7, "lot_id": lot_id, "roasted_on": day(10)})
    assert store.get_lot(conn, lot_id)["roasted_on"] == day(10)
    assert store.latest_score(conn, bean_id)["days_after_roast"] == 10


def test_score_does_not_overwrite_existing_lot_roast(conn):
    bean_id, lot_id = make_bean(conn, roasted_on=day(20))
    store.add_score(conn, bean_id, {"overall": 6, "lot_id": lot_id, "roasted_on": day(3)})
    assert store.get_lot(conn, lot_id)["roasted_on"] == day(20)
    assert store.latest_score(conn, bean_id)["roasted_on"] == day(3)
    assert store.latest_score(conn, bean_id)["days_after_roast"] == 3


def test_http_create_lot_and_plaza_score(client):
    bean = client.post(
        "/api/beans",
        json={
            "name": "广场焙日",
            "roast": "浅烘",
            "nominal_g": 200,
            "roasted_on": "2026-08-01",
            "visibility": "public",
        },
    ).json()
    assert bean["lots"][0]["roasted_on"] == "2026-08-01"
    assert bean["freshness"]["phase"] in ("resting", "peak", "fading", "stale")
    lot = client.post(
        f"/api/beans/{bean['id']}/lots",
        json={"nominal_g": 200, "roasted_on": "2026-07-01"},
    ).json()
    assert lot["roasted_on"] == "2026-07-01"
    assert client.patch(f"/api/lots/{lot['id']}", json={"roasted_on": "2099-01-01"}).status_code == 409
    client.post(f"/api/beans/{bean['id']}/scores", json={"overall": 8, "lot_id": bean["lots"][0]["id"]})
    card = client.get(f"/api/public/beans/{bean['id']}").json()
    assert card["scores"]["days_after_roast"] is not None
    assert card["scores"]["window_phase"] in ("resting", "peak", "fading", "stale")
    assert "lot_id" not in card["scores"]
    assert "lots" not in card
    assert "balance_g" not in card
