import os
import tempfile
from pathlib import Path

import pytest


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
    from app import store, stats, locks, main as main_mod

    importlib.reload(store)
    importlib.reload(stats)
    importlib.reload(locks)
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        yield c
