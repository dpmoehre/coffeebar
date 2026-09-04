"""平均粉量分层、杯数换算、统计排除撤回。"""

import pytest

from app import stats, store


def make_bean(conn, name="西达摩", nominal=200, price=128.0):
    bean_id = store.create_bean(conn, {"name": name})
    lot_id = store.add_lot(conn, bean_id, {"nominal_g": nominal, "price": price})
    return bean_id, lot_id


def test_fallback_when_no_history(conn):
    """一杯都没冲过才兜底 15 g，并说明还没数据。"""
    d = stats.average_dose(conn)
    assert d["avg_g"] == 15.0
    assert d["source"] == "fallback"
    assert d["cups"] == 0


def test_average_from_actual_amounts(conn):
    """平均粉量来自实际用量，不是假想值。"""
    _, lot_id = make_bean(conn)
    for g in (14, 16, 18):
        store.record_brew(conn, {"lot_id": lot_id, "amount_g": g})
    d = stats.average_dose(conn)
    assert d["avg_g"] == pytest.approx(16.0)
    assert (d["lo_g"], d["hi_g"]) == (14, 18), "要给区间，只给平均会掩盖波动"
    assert d["cups"] == 3


def test_voided_rows_excluded_from_average(conn):
    _, lot_id = make_bean(conn)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15})
    bad = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 30})
    assert stats.average_dose(conn)["avg_g"] == pytest.approx(22.5)

    store.void_consumption(conn, bad["id"])
    d = stats.average_dose(conn)
    assert d["avg_g"] == pytest.approx(15.0)
    assert d["cups"] == 1


def test_bean_average_preferred_over_global(conn):
    """这支豆有自己的历史就用它的，不用全局。"""
    a_id, a_lot = make_bean(conn, name="浅烘豆")
    b_id, b_lot = make_bean(conn, name="深烘豆")

    for _ in range(3):
        store.record_brew(conn, {"lot_id": a_lot, "amount_g": 20})
    store.record_brew(conn, {"lot_id": b_lot, "amount_g": 12})

    assert stats.average_dose(conn, a_id)["avg_g"] == pytest.approx(20.0)
    assert stats.average_dose(conn, a_id)["source"] == "bean"
    assert stats.average_dose(conn, b_id)["avg_g"] == pytest.approx(12.0)


def test_new_bean_falls_back_to_global(conn):
    """没冲过的新豆用全吧台平均，不用 15 g。"""
    _, lot_id = make_bean(conn, name="老豆")
    for g in (18, 18, 18):
        store.record_brew(conn, {"lot_id": lot_id, "amount_g": g})

    fresh = store.create_bean(conn, {"name": "刚买的"})
    d = stats.average_dose(conn, fresh)
    assert d["avg_g"] == pytest.approx(18.0)
    assert d["source"] == "global"


def test_cups_left_uses_average_not_fifteen(conn):
    """还能冲几杯按平均粉量换算。"""
    _, lot_id = make_bean(conn, nominal=200)
    for _ in range(3):
        store.record_brew(conn, {"lot_id": lot_id, "amount_g": 20})

    lot = store.get_lot(conn, lot_id)
    avg = stats.average_dose(conn)["avg_g"]
    assert avg == pytest.approx(20.0)
    assert stats.cups_left(lot["balance_g"], avg) == 7        # 140 / 20
    assert stats.cups_left(lot["balance_g"], 15) == 9         # 按 15 会高估


def test_summary_excludes_voided(conn):
    _, lot_id = make_bean(conn, nominal=500, price=250.0)
    keep = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16, "person": "丁瀚舟"})
    drop = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16, "person": "丁瀚舟"})
    store.void_consumption(conn, drop["id"])

    s = stats.summary(conn, "all")
    assert s["cups"] == 1
    assert s["beans_g"] == pytest.approx(16)
    assert s["spent"] == pytest.approx(16 * 250 / 500)
    assert sum(p["cups"] for p in s["by_person"]) == 1


def test_summary_separates_spent_from_bought(conn):
    """喝掉的钱和买进来的钱是两笔，不能混。"""
    _, lot_id = make_bean(conn, nominal=200, price=128.0)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})

    s = stats.summary(conn, "all")
    assert s["bought"] == pytest.approx(128.0)
    assert s["spent"] == pytest.approx(16 * 128 / 200)
    assert s["spent"] < s["bought"]


def test_person_rename_keeps_history(conn):
    """改名只改一行，历史记录跟着变。"""
    _, lot_id = make_bean(conn)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15, "person": "戚浩辰"})
    pid = store.ensure_person(conn, "戚浩辰")

    store.rename_person(conn, pid, "王工")

    rows = store.list_consumption(conn, limit=5)
    assert rows[0]["person_name"] == "王工"
    assert stats.person_profile(conn, pid)["cups"] == 1


def test_deactivate_hides_but_keeps(conn):
    """停用只是收起来，人和归属都还在。"""
    _, lot_id = make_bean(conn)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15, "person": "孙琦"})
    pid = store.ensure_person(conn, "孙琦")

    store.set_person_active(conn, pid, False)

    assert all(p["name"] != "孙琦" for p in store.list_people(conn))
    assert any(p["name"] == "孙琦" for p in store.list_people(conn, include_inactive=True))
    assert stats.person_profile(conn, pid)["cups"] == 1


def test_delete_person_orphans_rows_but_keeps_totals(conn):
    """删人：人没了，流水留着变「没记」，库存和总数一动不动。"""
    _, lot_id = make_bean(conn, nominal=200)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16, "person": "戚浩辰"})
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15, "person": "丁瀚舟"})
    pid = store.ensure_person(conn, "戚浩辰")

    before = stats.summary(conn, "all")
    balance_before = store.get_lot(conn, lot_id)["balance_g"]

    out = store.delete_person(conn, pid)
    assert out == {"name": "戚浩辰", "orphaned": 1}

    assert all(p["name"] != "戚浩辰" for p in store.list_people(conn, include_inactive=True))

    after = stats.summary(conn, "all")
    assert after["cups"] == before["cups"] == 2, "流水没被删"
    assert after["beans_g"] == before["beans_g"] == pytest.approx(31)
    assert after["spent"] == pytest.approx(before["spent"]), "钱是真花过的，不能凭空消失"
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(balance_before)

    names = {p["name"] for p in after["by_person"]}
    assert names == {"丁瀚舟", "没记"}, "他那笔归到「没记」，不再算在任何人头上"


def test_delete_person_without_records(conn):
    pid = store.ensure_person(conn, "路人")
    assert store.delete_person(conn, pid) == {"name": "路人", "orphaned": 0}
    assert store.list_people(conn, include_inactive=True) == []


def test_delete_person_leaves_audit_trail(conn):
    """删人要留痕，否则没法回答「这笔以前是谁的」。"""
    _, lot_id = make_bean(conn)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16, "person": "戚浩辰"})
    store.delete_person(conn, store.ensure_person(conn, "戚浩辰"))

    audit = conn.execute("SELECT field, old_value, new_value FROM consumption_audit").fetchone()
    assert (audit[0], audit[1], audit[2]) == ("person", "戚浩辰", None)


def test_delete_missing_person(conn):
    with pytest.raises(store.Conflict, match="没有这个人"):
        store.delete_person(conn, 999)


def test_reassign_before_delete_keeps_attribution(conn):
    """想把记录留给别人：先改归属再删，那笔就不会变成「没记」。"""
    _, lot_id = make_bean(conn)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16, "person": "戚浩辰"})
    store.reassign_person(conn, res["id"], "孙琦")

    out = store.delete_person(conn, store.ensure_person(conn, "戚浩辰"))
    assert out["orphaned"] == 0
    assert store.list_consumption(conn, limit=1)[0]["person_name"] == "孙琦"


def test_people_list_carries_record_count(conn):
    """删之前要能告诉人「他名下有几条」。"""
    _, lot_id = make_bean(conn)
    for _ in range(3):
        store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15, "person": "戚浩辰"})
    bad = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15, "person": "戚浩辰"})
    store.void_consumption(conn, bad["id"])

    person = store.list_people(conn)[0]
    assert person["cups"] == 3, "撤回的不算进条数"


def test_reassign_person_keeps_stock(conn):
    """人选错了只改归属，克重和库存不动。"""
    _, lot_id = make_bean(conn, nominal=200)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16, "person": "戚浩辰"})
    before = store.get_lot(conn, lot_id)["balance_g"]

    store.reassign_person(conn, res["id"], "孙琦")

    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(before)
    assert store.list_consumption(conn, limit=1)[0]["person_name"] == "孙琦"
    audit = conn.execute("SELECT old_value, new_value FROM consumption_audit").fetchone()
    assert (audit[0], audit[1]) == ("戚浩辰", "孙琦"), "改归属要留痕"


def test_restock_flags_not_enough_for_one_cup(conn):
    _, lot_id = make_bean(conn, nominal=200)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})
    store.adjust_lot(conn, lot_id, 10)  # 盘到只剩 10 g

    items = stats.restock_list(conn)
    assert len(items) == 1
    assert "不够一杯了" in items[0]["reasons"]
    assert items[0]["cups_left"] == 0
