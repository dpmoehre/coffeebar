"""HTTP 共用依赖。路由从这里拿连接和当前账号，不各自再写一遍。"""

from __future__ import annotations

import sqlite3

from fastapi import Depends, Request

from . import auth, db


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_account(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return auth.require_account(request, conn)


def current_admin(account: dict = Depends(current_account)) -> dict:
    return auth.require_admin(account)


def optional_account(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict | None:
    return auth.account_from_token(conn, auth.cookie_token(request))
