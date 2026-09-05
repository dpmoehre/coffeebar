"""账面剩余、成本快照、撤回——三条最容易出错的口径。"""

import pytest

from app import stats, store


def make_bean(conn, nominal=200, price=128.0):
    bean_id = store.create_bean(conn, {"name": "西达摩 水洗", "roast": "浅烘"})
    lot_id = store.add_lot(conn, bean_id, {"nominal_g": nominal, "price": price})
    return bean_id, lot_id


def test_fresh_lot_uses_nominal_not_measured(conn):
    """刚拆袋不会称，默认按包装标称扣。"""
    _, lot_id = make_bean(conn, nominal=200)
    lot = store.get_lot(conn, lot_id)
    assert lot["measured_g"] is None
    assert lot["usable_g"] == 200
    assert lot["balance_g"] == 200


def test_balance_drops_by_actual_amount(conn):
    """扣的是当次实际用量，不是固定 15 g。"""
    _, lot_id = make_bean(conn)
    for g in (16, 14.5, 18):
        store.record_brew(conn, {"lot_id": lot_id, "amount_g": g})
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(200 - 48.5)


def test_measure_replaces_usable_weight(conn):
    """补了开袋实称，可用克重与账面都跟着变。"""
    _, lot_id = make_bean(conn, nominal=200)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})
    store.set_measured(conn, lot_id, 194)
    lot = store.get_lot(conn, lot_id)
    assert lot["usable_g"] == 194
    assert lot["balance_g"] == pytest.approx(194 - 16)


def test_unit_cost_snapshot_survives_measure(conn):
    """核心：改实称不能回溯改写已经发生的那笔钱。"""
    _, lot_id = make_bean(conn, nominal=200, price=128.0)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})
    cost_before = res["cost"]
    assert cost_before == pytest.approx(16 * 128 / 200)

    store.set_measured(conn, lot_id, 150)  # 分母变小，若回溯重算这笔会变贵

    row = store.list_consumption(conn, limit=1)[0]
    assert row["unit_cost"] == pytest.approx(128 / 200)
    assert row["cost"] == pytest.approx(cost_before)


def test_adjust_records_difference(conn):
    """盘点：人输入现在实际剩多少，系统记差额。"""
    _, lot_id = make_bean(conn, nominal=200)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 20})
    delta = store.adjust_lot(conn, lot_id, 170)  # 账面 180，实际 170
    assert delta == pytest.approx(-10)
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(170)


def test_close_lot_zeroes_balance_and_reports_deviation(conn):
    """这袋用完：余数记成偏差，账面归零。"""
    _, lot_id = make_bean(conn, nominal=200)
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 190})
    deviation = store.close_lot(conn, lot_id)
    assert deviation == pytest.approx(10)
    lot = store.get_lot(conn, lot_id)
    assert lot["closed_at"] is not None
    assert lot["balance_g"] == pytest.approx(0)


def test_cannot_brew_from_closed_lot(conn):
    _, lot_id = make_bean(conn)
    store.close_lot(conn, lot_id)
    with pytest.raises(store.Conflict, match="已经关了"):
        store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15})


def test_cannot_overdraw(conn):
    """不够就提示，不静默扣成负数。"""
    _, lot_id = make_bean(conn, nominal=20)
    with pytest.raises(store.Conflict, match="不够"):
        store.record_brew(conn, {"lot_id": lot_id, "amount_g": 25})


def test_void_returns_grams_and_leaves_row(conn):
    """撤回：库存加回去，行还在（只是划掉）。"""
    _, lot_id = make_bean(conn, nominal=200)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(184)

    store.void_consumption(conn, res["id"], "记错了")
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(200)

    rows = store.list_consumption(conn, limit=10)
    assert len(rows) == 1, "撤回不物理删除"
    assert rows[0]["voided_at"] is not None
    assert rows[0]["void_reason"] == "记错了"


def test_void_twice_rejected(conn):
    _, lot_id = make_bean(conn)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15})
    store.void_consumption(conn, res["id"])
    with pytest.raises(store.Conflict, match="已经撤回"):
        store.void_consumption(conn, res["id"])


def test_void_on_closed_lot_keeps_balance_zero(conn):
    """已关袋批次撤回：不改已结清的偏差，差额记成当天新调整。"""
    _, lot_id = make_bean(conn, nominal=200)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})
    store.close_lot(conn, lot_id)
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(0)

    out = store.void_consumption(conn, res["id"])
    assert out["closed_lot_adjusted"] is True
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(0), "关袋结果不能被撤回破坏"

    kinds = [
        r[0]
        for r in conn.execute(
            "SELECT kind FROM stock_event WHERE lot_id = ? ORDER BY id", (lot_id,)
        ).fetchall()
    ]
    assert kinds == ["intake", "close_lot", "adjust"]


def test_unvoid_restores(conn):
    _, lot_id = make_bean(conn, nominal=200)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})
    store.void_consumption(conn, res["id"])
    store.unvoid_consumption(conn, res["id"])
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(184)


def test_delete_voided_removes_row_keeps_balance(conn):
    """彻底删只抹掉已撤回的行，账面不再动。"""
    _, lot_id = make_bean(conn, nominal=200)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})
    store.void_consumption(conn, res["id"])
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(200)

    store.delete_voided_consumption(conn, res["id"])
    assert store.list_consumption(conn, limit=10) == []
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(200)


def test_delete_active_rejected(conn):
    _, lot_id = make_bean(conn)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15})
    with pytest.raises(store.Conflict, match="先撤回再删"):
        store.delete_voided_consumption(conn, res["id"])
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(185)


def test_delete_voided_on_closed_lot_keeps_adjust(conn):
    """已关袋撤回留下的当天调整还在，删记录不改那袋账面。"""
    _, lot_id = make_bean(conn, nominal=200)
    res = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 16})
    store.close_lot(conn, lot_id)
    store.void_consumption(conn, res["id"])
    store.delete_voided_consumption(conn, res["id"])
    assert store.get_lot(conn, lot_id)["balance_g"] == pytest.approx(0)
    kinds = [
        r[0]
        for r in conn.execute(
            "SELECT kind FROM stock_event WHERE lot_id = ? ORDER BY id", (lot_id,)
        ).fetchall()
    ]
    assert kinds == ["intake", "close_lot", "adjust"]


def test_multiple_lots_are_chosen_explicitly(conn):
    """同一支豆几袋并存，扣哪袋由调用方指定，不自动 FIFO。"""
    bean_id, first = make_bean(conn, nominal=200, price=118.0)
    second = store.add_lot(conn, bean_id, {"nominal_g": 200, "price": 128.0})

    store.record_brew(conn, {"lot_id": second, "amount_g": 16})

    assert store.get_lot(conn, first)["balance_g"] == pytest.approx(200), "没被选中的袋不能动"
    assert store.get_lot(conn, second)["balance_g"] == pytest.approx(184)

    row = store.list_consumption(conn, limit=1)[0]
    assert row["unit_cost"] == pytest.approx(128 / 200), "钱按被选中那袋的单价算"


def test_lots_numbered_by_purchase_order(conn):
    """两袋规格价钱一样时要能分清谁是谁，编号按买入顺序且不随开封改变。"""
    bean_id, _ = make_bean(conn, nominal=500, price=380.0)
    second = store.add_lot(conn, bean_id, {"nominal_g": 500, "price": 380.0})

    assert [l["seq"] for l in store.list_lots(conn, bean_id)] == [1, 2]

    store.open_lot(conn, second)
    lots = store.list_lots(conn, bean_id)
    assert lots[0]["id"] == second, "在喝的那袋排前面"
    assert lots[0]["seq"] == 2, "第 2 袋永远是第 2 袋，编号不跟显示顺序走"

    store.record_brew(conn, {"lot_id": second, "amount_g": 16})
    assert store.list_consumption(conn, limit=1)[0]["lot_seq"] == 2, "日志说得清是哪一袋"


def test_library_unit_cost_is_price_over_usable(conn):
    """豆库克价 = 买入价 ÷ 可用克重（没实称就用袋上印的）。"""
    make_bean(conn, nominal=227, price=102.0)
    card = store.list_beans(conn)[0]
    assert card["unit_cost"] == pytest.approx(102 / 227)


def test_library_unit_cost_weights_remaining_across_bags(conn):
    """两袋价钱不一样，克价按还剩的克加权，不拿袋数平均。"""
    bean_id, cheap = make_bean(conn, nominal=200, price=80.0)   # 0.40 元/g
    store.add_lot(conn, bean_id, {"nominal_g": 200, "price": 160.0})  # 0.80
    # 便宜那袋喝掉一半，贵的还满着：加权 = (100*0.4 + 200*0.8) / 300 = 0.666…
    store.record_brew(conn, {"lot_id": cheap, "amount_g": 100})
    card = store.list_beans(conn)[0]
    assert card["unit_cost"] == pytest.approx((100 * 0.4 + 200 * 0.8) / 300)
    assert store.get_bean(conn, bean_id)["unit_cost"] == pytest.approx(card["unit_cost"])


def test_library_unit_cost_none_without_price(conn):
    bean_id = store.create_bean(conn, {"name": "没标价"})
    store.add_lot(conn, bean_id, {"nominal_g": 200})
    assert store.list_beans(conn)[0]["unit_cost"] is None


def test_history_keeps_last_bag_unit_cost(conn):
    """喝完进历史也留着克价，排序还能按价钱翻旧豆。"""
    bean_id, lot_id = make_bean(conn, nominal=200, price=128.0)
    store.close_lot(conn, lot_id)
    hist = store.list_beans(conn, scope="history")
    assert hist[0]["unit_cost"] == pytest.approx(128 / 200)


def test_first_brew_sets_opened_on(conn):
    _, lot_id = make_bean(conn)
    assert store.get_lot(conn, lot_id)["opened_on"] is None
    store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15})
    assert store.get_lot(conn, lot_id)["opened_on"] is not None
