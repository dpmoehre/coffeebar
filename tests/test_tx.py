import sqlite3

import pytest

from app import db, store


def test_transaction_rolls_back(conn):
    store.create_bean(conn, {"name": "事务豆"})
    before = conn.execute("SELECT COUNT(*) FROM bean").fetchone()[0]
    with pytest.raises(RuntimeError):
        with db.transaction(conn):
            conn.execute("UPDATE bean SET name = '改过了'")
            raise RuntimeError("boom")
    after = conn.execute("SELECT COUNT(*) FROM bean").fetchone()[0]
    name = conn.execute("SELECT name FROM bean").fetchone()[0]
    assert after == before
    assert name == "事务豆"


def test_void_inner_failure_keeps_row(conn, monkeypatch):
    bean_id = store.create_bean(conn, {"name": "撤回豆"})
    lot_id = store.add_lot(conn, bean_id, {"nominal_g": 200, "price": 80})
    ev = store.record_brew(conn, {"lot_id": lot_id, "amount_g": 15, "brew_method": "v60"})

    def boom(*_a, **_k):
        raise sqlite3.OperationalError("simulated")

    monkeypatch.setattr(store, "get_lot", boom)
    with pytest.raises(sqlite3.OperationalError):
        store.void_one(conn, ev["id"], "试回滚")
    row = conn.execute(
        "SELECT voided_at FROM consumption_event WHERE id = ?", (ev["id"],)
    ).fetchone()
    assert row["voided_at"] is None
