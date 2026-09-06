import os
import tempfile
from pathlib import Path

import pytest

# 套件里会连续注册/登录，默认限流会误伤。单独测限流的用例再打开。
os.environ["COFFEEBAR_RATE_LIMIT"] = "0"
os.environ["COFFEEBAR_STARTER_BEAN"] = "0"
os.environ.pop("COFFEEBAR_INVITE_CODE", None)
os.environ.pop("COFFEEBAR_RESTORE_KEY", None)


@pytest.fixture()
def conn(monkeypatch):
    """每个用例一份独立的临时库。"""
    tmp = tempfile.mkdtemp(prefix="coffeebar-test-")
    os.environ["COFFEEBAR_DATA"] = tmp

    from app import db as db_mod
    import importlib

    importlib.reload(db_mod)
    c = db_mod.connect()
    db_mod.init_db(c)
    yield c
    c.close()


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="coffeebar-api-")
    os.environ["COFFEEBAR_DATA"] = tmp

    import importlib
    from fastapi.testclient import TestClient

    from app import db as db_mod

    importlib.reload(db_mod)
    from app import freshness, store, stats, locks, photos, places, spirits, ledger, auth, menu, admin, brew, gear, kingdom, kingdom_gear, today, people, deps, main as main_mod
    from app.routers import (
        admin_http,
        auth as auth_rt,
        beans as beans_rt,
        brews as brews_rt,
        gear as gear_rt,
        kingdom as kingdom_rt,
        menu as menu_rt,
        ops as ops_rt,
        people as people_rt,
        plaza as plaza_rt,
        spirits as spirits_rt,
        stats as stats_rt,
        writelocks as writelocks_rt,
    )

    importlib.reload(freshness)
    importlib.reload(photos)
    importlib.reload(places)
    importlib.reload(people)
    importlib.reload(store)
    importlib.reload(spirits)
    importlib.reload(menu)
    importlib.reload(stats)
    importlib.reload(ledger)
    importlib.reload(locks)
    importlib.reload(auth)
    importlib.reload(admin)
    importlib.reload(brew)
    importlib.reload(gear)
    importlib.reload(kingdom)
    importlib.reload(kingdom_gear)
    importlib.reload(today)
    importlib.reload(deps)
    for _rt in (
        auth_rt, beans_rt, gear_rt, brews_rt, spirits_rt, menu_rt, people_rt,
        stats_rt, writelocks_rt, kingdom_rt, plaza_rt, admin_http, ops_rt,
    ):
        importlib.reload(_rt)
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        r = c.post(
            "/api/auth/register",
            json={"email": "test@coffeebar.local", "password": "testpass1"},
        )
        assert r.status_code == 201, r.text
        yield c
