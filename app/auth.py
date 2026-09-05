"""账号与登录会话。写锁仍用 X-Session（哪台设备在改）；身份用 cookie。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import timedelta

from fastapi import HTTPException, Request, Response

from . import db

COOKIE = "coffeebar_auth"
ITERATIONS = 200_000
SESSION_DAYS = 30


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${dk.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
    return hmac.compare_digest(dk.hex(), digest)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def public_account(row: sqlite3.Row | dict) -> dict:
    return {"id": row["id"], "email": row["email"]}


def get_account(conn: sqlite3.Connection, account_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM account WHERE id = ?", (account_id,)).fetchone()
    return dict(row) if row else None


def register(conn: sqlite3.Connection, email: str, password: str) -> dict:
    email = normalize_email(email)
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "邮箱不像邮箱")
    if len(password) < 8:
        raise HTTPException(400, "密码至少 8 个字符")
    if conn.execute("SELECT id FROM account WHERE email = ?", (email,)).fetchone():
        raise HTTPException(409, "这个邮箱已经注册过了")
    first = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0
    cur = conn.execute(
        "INSERT INTO account (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, hash_password(password), db.now()),
    )
    account_id = int(cur.lastrowid)
    if first:
        claim_orphans(conn, account_id)
    return {"id": account_id, "email": email, "claimed": first}


def login(conn: sqlite3.Connection, email: str, password: str) -> dict:
    email = normalize_email(email)
    row = conn.execute("SELECT * FROM account WHERE email = ?", (email,)).fetchone()
    if not row or row["status"] != "active" or not check_password(password, row["password_hash"]):
        raise HTTPException(401, "邮箱或密码不对")
    return public_account(row)


def claim_orphans(conn: sqlite3.Connection, account_id: int) -> None:
    """第一个账号接手老库里还没主人的豆、酒、人。小主机升级时走这里。"""
    conn.execute("UPDATE bean SET owner_id = ? WHERE owner_id IS NULL", (account_id,))
    conn.execute("UPDATE bottle SET owner_id = ? WHERE owner_id IS NULL", (account_id,))
    conn.execute("UPDATE person SET owner_id = ? WHERE owner_id IS NULL", (account_id,))


def issue_session(conn: sqlite3.Connection, account_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = db.now()
    expires = (db.parse(now) + timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat(sep=" ")
    conn.execute(
        "INSERT INTO auth_session (token, account_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, account_id, now, expires),
    )
    return token


def drop_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM auth_session WHERE token = ?", (token,))


def account_from_token(conn: sqlite3.Connection, token: str | None) -> dict | None:
    if not token:
        return None
    row = conn.execute(
        """SELECT a.* FROM account a
           JOIN auth_session s ON s.account_id = a.id
           WHERE s.token = ? AND s.expires_at > ? AND a.status = 'active'""",
        (token, db.now()),
    ).fetchone()
    return dict(row) if row else None


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def cookie_token(request: Request) -> str | None:
    return request.cookies.get(COOKIE)


def require_account(request: Request, conn: sqlite3.Connection) -> dict:
    account = account_from_token(conn, cookie_token(request))
    if not account:
        raise HTTPException(401, "请先登录")
    return account


def bean_owner(conn: sqlite3.Connection, bean_id: int) -> int | None:
    row = conn.execute("SELECT owner_id FROM bean WHERE id = ?", (bean_id,)).fetchone()
    return None if not row else row["owner_id"]


def lot_bean_owner(conn: sqlite3.Connection, lot_id: int) -> int | None:
    row = conn.execute(
        "SELECT b.owner_id FROM bean_lot l JOIN bean b ON b.id = l.bean_id WHERE l.id = ?",
        (lot_id,),
    ).fetchone()
    return None if not row else row["owner_id"]


def spirit_owner(conn: sqlite3.Connection, bottle_id: int) -> int | None:
    row = conn.execute("SELECT owner_id FROM bottle WHERE id = ?", (bottle_id,)).fetchone()
    return None if not row else row["owner_id"]


def bottle_lot_owner(conn: sqlite3.Connection, lot_id: int) -> int | None:
    row = conn.execute(
        """SELECT b.owner_id FROM bottle_lot l
           JOIN bottle b ON b.id = l.bottle_id WHERE l.id = ?""",
        (lot_id,),
    ).fetchone()
    return None if not row else row["owner_id"]


def person_owner(conn: sqlite3.Connection, person_id: int) -> int | None:
    row = conn.execute("SELECT owner_id FROM person WHERE id = ?", (person_id,)).fetchone()
    return None if not row else row["owner_id"]


def consumption_owner(conn: sqlite3.Connection, cons_id: int) -> int | None:
    row = conn.execute(
        """SELECT COALESCE(b.owner_id, sp.owner_id) AS owner_id
           FROM consumption_event c
           LEFT JOIN bean_lot l ON l.id = c.lot_id
           LEFT JOIN bean b ON b.id = l.bean_id
           LEFT JOIN bottle_lot bl ON bl.id = c.bottle_lot_id
           LEFT JOIN bottle sp ON sp.id = bl.bottle_id
           WHERE c.id = ?""",
        (cons_id,),
    ).fetchone()
    return None if not row else row["owner_id"]


def assert_owner(owner_id: int | None, account_id: int, message: str) -> None:
    if owner_id is None or owner_id != account_id:
        raise HTTPException(404, message)


def assert_lock_resource(conn: sqlite3.Connection, resource: str, account_id: int) -> None:
    kind, _, sid = resource.partition(":")
    if not sid.isdigit():
        raise HTTPException(400, "锁的资源不对")
    rid = int(sid)
    if kind == "bean":
        assert_owner(bean_owner(conn, rid), account_id, "没有这支豆")
    elif kind == "bottle":
        assert_owner(spirit_owner(conn, rid), account_id, "没有这支酒")
    else:
        raise HTTPException(400, "锁的资源不对")
