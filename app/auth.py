"""账号与登录会话。写锁仍用 X-Session（哪台设备在改）；身份用 cookie。"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, Response

from . import db, mail

COOKIE = "coffeebar_auth"
ITERATIONS = 200_000
SESSION_DAYS = 30
TOKEN_HOURS = 2
EXPORT_MINUTES = 15
HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    return HASHER.hash(password)


def check_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2"):
        try:
            HASHER.verify(stored, password)
            return True
        except (VerifyMismatchError, ValueError):
            return False
    try:
        algo, iters, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
    return hmac.compare_digest(dk.hex(), digest)


def needs_rehash(stored: str) -> bool:
    if not stored.startswith("$argon2"):
        return True
    try:
        return HASHER.check_needs_rehash(stored)
    except Exception:
        return False


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


DEFAULT_ADMIN_EMAIL = "1821601734@qq.com"


def admin_emails() -> frozenset[str]:
    extra = {
        normalize_email(x)
        for x in (os.environ.get("COFFEEBAR_ADMIN_EMAILS") or "").split(",")
        if x.strip()
    }
    return frozenset({DEFAULT_ADMIN_EMAIL} | extra)


def is_admin_email(email: str) -> bool:
    return normalize_email(email) in admin_emails()


def is_admin(account: dict | None) -> bool:
    return bool(account) and is_admin_email(account.get("email") or "")


def require_admin(account: dict) -> dict:
    if not is_admin(account):
        raise HTTPException(403, "只有管理员能进这里")
    return account


def public_account(row: sqlite3.Row | dict) -> dict:
    try:
        verified = row["email_verified"]
    except (KeyError, IndexError):
        verified = 1
    email = row["email"]
    return {
        "id": row["id"],
        "email": email,
        "email_verified": bool(verified),
        "admin": is_admin_email(email),
    }


def get_account(conn: sqlite3.Connection, account_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM account WHERE id = ?", (account_id,)).fetchone()
    return dict(row) if row else None


def invite_required() -> bool:
    return bool((os.environ.get("COFFEEBAR_INVITE_CODE") or "").strip())


def require_invite(invite: str | None) -> None:
    expected = (os.environ.get("COFFEEBAR_INVITE_CODE") or "").strip()
    if not expected:
        return
    got = (invite or "").strip()
    if len(got) != len(expected) or not hmac.compare_digest(got, expected):
        raise HTTPException(403, "邀请码不对")


class OrphansPending(Exception):
    def __init__(self, counts: dict):
        self.counts = counts
        super().__init__("这台机器上还有没主人的库存，请选择接手或只要空库")


CLAIM_TABLES = ("bean", "bottle", "person", "recipe", "menu_item", "drink_serve", "user_gear")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return bool(row)


def orphan_counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {"beans": 0, "bottles": 0, "people": 0, "recipes": 0}
    mapping = {
        "bean": "beans",
        "bottle": "bottles",
        "person": "people",
        "recipe": "recipes",
        "menu_item": "recipes",
        "drink_serve": "recipes",
        "user_gear": "recipes",
    }
    for table, key in mapping.items():
        if not _table_exists(conn, table):
            continue
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "owner_id" not in cols:
            continue
        n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE owner_id IS NULL").fetchone()[0]
        out[key] = out.get(key, 0) + int(n)
    return out


def has_orphans(conn: sqlite3.Connection) -> bool:
    return any(orphan_counts(conn).values())


def earliest_account_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM account ORDER BY id ASC LIMIT 1").fetchone()
    return None if not row else int(row["id"])


def can_claim(conn: sqlite3.Connection, account_id: int) -> bool:
    earliest = earliest_account_id(conn)
    return earliest is not None and earliest == account_id


def is_stock_account(conn: sqlite3.Connection, account_id: int) -> bool:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(account)")}
    if "claimed_at" in cols:
        row = conn.execute("SELECT claimed_at FROM account WHERE id = ?", (account_id,)).fetchone()
        if row and row["claimed_at"]:
            return True
    beans = conn.execute(
        "SELECT COUNT(*) FROM bean WHERE owner_id = ? AND (deleted_at IS NULL OR deleted_at = '')",
        (account_id,),
    ).fetchone()[0]
    bottles = conn.execute(
        "SELECT COUNT(*) FROM bottle WHERE owner_id = ? AND (deleted_at IS NULL OR deleted_at = '')",
        (account_id,),
    ).fetchone()[0]
    return int(beans) + int(bottles) > 0


def mark_claimed(conn: sqlite3.Connection, account_id: int) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(account)")}
    if "claimed_at" in cols:
        conn.execute(
            "UPDATE account SET claimed_at = COALESCE(claimed_at, ?) WHERE id = ?",
            (db.now(), account_id),
        )


def stock_flags(conn: sqlite3.Connection, account_id: int) -> dict:
    counts = orphan_counts(conn)
    claimable = can_claim(conn, account_id) and any(counts.values())
    return {
        "claimed": is_stock_account(conn, account_id),
        "can_claim": claimable,
        "orphans": counts if claimable else None,
    }


def register(
    conn: sqlite3.Connection,
    email: str,
    password: str,
    invite: str | None = None,
    claim: str | None = None,
) -> dict:
    require_invite(invite)
    email = normalize_email(email)
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "邮箱不像邮箱")
    if len(password) < 8:
        raise HTTPException(400, "密码至少 8 个字符")
    if conn.execute("SELECT id FROM account WHERE email = ?", (email,)).fetchone():
        raise HTTPException(409, "这个邮箱已经注册过了")
    orphans = orphan_counts(conn)
    pending = any(orphans.values())
    choice = (claim or "").strip().lower() or None
    if pending and choice not in ("take", "leave"):
        raise OrphansPending(orphans)
    if pending and choice == "take" and earliest_account_id(conn) is not None:
        raise HTTPException(403, "只有这台机器上最早的账号能接手库存")
    verified = 0 if mail.configured() else 1
    with db.transaction(conn):
        cur = conn.execute(
            """INSERT INTO account (email, password_hash, email_verified, created_at)
               VALUES (?, ?, ?, ?)""",
            (email, hash_password(password), verified, db.now()),
        )
        account_id = int(cur.lastrowid)
        claimed = False
        if pending and choice == "take":
            claim_orphans(conn, account_id)
            mark_claimed(conn, account_id)
            claimed = True
        verify_token = None
        if not verified:
            verify_token = issue_token(conn, account_id, "verify")
    return {
        "id": account_id,
        "email": email,
        "claimed": claimed,
        "email_verified": bool(verified),
        "verify_token": verify_token,
    }


def claim_now(conn: sqlite3.Connection, account: dict) -> dict:
    aid = int(account["id"])
    if not can_claim(conn, aid):
        raise HTTPException(403, "只有这台机器上最早的账号能接手库存")
    if not has_orphans(conn):
        raise HTTPException(400, "没有没主人的库存")
    with db.transaction(conn):
        claim_orphans(conn, aid)
        mark_claimed(conn, aid)
    return {"ok": True, "claimed": True}


def login(conn: sqlite3.Connection, email: str, password: str) -> dict:
    email = normalize_email(email)
    row = conn.execute("SELECT * FROM account WHERE email = ?", (email,)).fetchone()
    if not row or row["status"] != "active" or not check_password(password, row["password_hash"]):
        raise HTTPException(401, "邮箱或密码不对")
    if needs_rehash(row["password_hash"]):
        conn.execute(
            "UPDATE account SET password_hash = ? WHERE id = ?",
            (hash_password(password), row["id"]),
        )
    return public_account(row)


def claim_orphans(conn: sqlite3.Connection, account_id: int) -> None:
    """接手老库里还没主人的豆、酒、人、酒单。"""
    for table in CLAIM_TABLES:
        if not _table_exists(conn, table):
            continue
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "owner_id" not in cols:
            continue
        conn.execute(f"UPDATE {table} SET owner_id = ? WHERE owner_id IS NULL", (account_id,))


def peek_export_token(conn: sqlite3.Connection, token: str | None, account_id: int) -> bool:
    if not token:
        return False
    row = conn.execute("SELECT * FROM auth_token WHERE token = ?", (token,)).fetchone()
    if (
        not row
        or row["purpose"] != "export"
        or row["used_at"]
        or int(row["account_id"]) != account_id
        or row["expires_at"] <= db.now()
    ):
        return False
    return True


def consume_export_token(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("UPDATE auth_token SET used_at = ? WHERE token = ?", (db.now(), token))


def delete_account(
    conn: sqlite3.Connection,
    account: dict,
    email: str,
    password: str,
    export_token: str | None = None,
) -> None:
    """注销：核过邮箱和密码后，删掉这个人的豆、酒、人、照片和账号。不可恢复。"""
    if normalize_email(email) != normalize_email(account["email"]):
        raise HTTPException(400, "请输入这个账号的邮箱")
    row = conn.execute("SELECT password_hash FROM account WHERE id = ?", (account["id"],)).fetchone()
    if not row or not check_password(password, row["password_hash"]):
        raise HTTPException(401, "密码不对")
    aid = int(account["id"])
    if is_stock_account(conn, aid) and not peek_export_token(conn, export_token, aid):
        raise HTTPException(400, "先导出备份")
    from . import photos

    paths = photos.paths_for_owner(conn, aid)
    # SQLite：事务里改 foreign_keys 要等 COMMIT 才生效，必须先关再 BEGIN
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with db.transaction(conn):
            if export_token:
                consume_export_token(conn, export_token)
            conn.execute(
                """DELETE FROM write_lock WHERE resource IN (
                     SELECT 'bean:' || id FROM bean WHERE owner_id = ?
                     UNION
                     SELECT 'bottle:' || id FROM bottle WHERE owner_id = ?
                     UNION
                     SELECT 'recipe:' || id FROM recipe WHERE owner_id = ?
                   )""",
                (aid, aid, aid),
            )
            conn.execute(
                """UPDATE consumption_event SET person_id = NULL
                   WHERE person_id IN (SELECT id FROM person WHERE owner_id = ?)""",
                (aid,),
            )
            cons_owned = """
                SELECT c.id FROM consumption_event c
                LEFT JOIN bean_lot l ON l.id = c.lot_id
                LEFT JOIN bean b ON b.id = l.bean_id
                LEFT JOIN bottle_lot bl ON bl.id = c.bottle_lot_id
                LEFT JOIN bottle sp ON sp.id = bl.bottle_id
                WHERE b.owner_id = ? OR sp.owner_id = ?
            """
            conn.execute(f"DELETE FROM consumption_photo WHERE cons_id IN ({cons_owned})", (aid, aid))
            conn.execute(f"DELETE FROM consumption_audit WHERE cons_id IN ({cons_owned})", (aid, aid))
            conn.execute(f"DELETE FROM consumption_event WHERE id IN ({cons_owned})", (aid, aid))
            conn.execute("DELETE FROM drink_serve WHERE owner_id = ?", (aid,))
            conn.execute("DELETE FROM menu_item WHERE owner_id = ?", (aid,))
            conn.execute("DELETE FROM recipe WHERE owner_id = ?", (aid,))
            conn.execute("DELETE FROM bean WHERE owner_id = ?", (aid,))
            conn.execute("DELETE FROM bottle WHERE owner_id = ?", (aid,))
            conn.execute("DELETE FROM person WHERE owner_id = ?", (aid,))
            if _table_exists(conn, "user_gear"):
                conn.execute(
                    """UPDATE gear_catalog SET source_gear_id = NULL
                       WHERE source_gear_id IN (SELECT id FROM user_gear WHERE owner_id = ?)""",
                    (aid,),
                )
                conn.execute(
                    "UPDATE gear_catalog SET collected_by = NULL WHERE collected_by = ?", (aid,)
                )
                conn.execute(
                    """DELETE FROM user_gear_photo
                       WHERE gear_id IN (SELECT id FROM user_gear WHERE owner_id = ?)""",
                    (aid,),
                )
                conn.execute("DELETE FROM user_gear WHERE owner_id = ?", (aid,))
            if _table_exists(conn, "kingdom_score"):
                conn.execute("DELETE FROM kingdom_score WHERE author_id = ?", (aid,))
            if _table_exists(conn, "kingdom_favorite"):
                conn.execute("DELETE FROM kingdom_favorite WHERE account_id = ?", (aid,))
            if _table_exists(conn, "kingdom_bean"):
                conn.execute(
                    "UPDATE kingdom_bean SET collected_by = NULL WHERE collected_by = ?", (aid,)
                )
            conn.execute("DELETE FROM auth_token WHERE account_id = ?", (aid,))
            conn.execute("DELETE FROM auth_session WHERE account_id = ?", (aid,))
            conn.execute("DELETE FROM account WHERE id = ?", (aid,))
    except sqlite3.Error as exc:
        raise HTTPException(500, f"注销没做成：{exc}") from exc
    finally:
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error:
            pass
    for path in paths:
        photos.remove(path)


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


def drop_all_sessions(conn: sqlite3.Connection, account_id: int) -> None:
    conn.execute("DELETE FROM auth_session WHERE account_id = ?", (account_id,))


def drop_other_sessions(conn: sqlite3.Connection, account_id: int, keep_token: str | None) -> None:
    if keep_token:
        conn.execute(
            "DELETE FROM auth_session WHERE account_id = ? AND token != ?",
            (account_id, keep_token),
        )
    else:
        drop_all_sessions(conn, account_id)


def change_password(conn: sqlite3.Connection, account: dict, old: str, new: str) -> None:
    if len(new or "") < 8:
        raise HTTPException(400, "密码至少 8 个字符")
    row = conn.execute("SELECT password_hash FROM account WHERE id = ?", (account["id"],)).fetchone()
    if not row or not check_password(old or "", row["password_hash"]):
        raise HTTPException(401, "现在的密码不对")
    if check_password(new, row["password_hash"]):
        raise HTTPException(400, "新密码要和现在的不一样")
    conn.execute(
        "UPDATE account SET password_hash = ? WHERE id = ?",
        (hash_password(new), account["id"]),
    )


def issue_token(conn: sqlite3.Connection, account_id: int, purpose: str) -> str:
    token = secrets.token_urlsafe(32)
    now = db.now()
    expires = (db.parse(now) + timedelta(hours=TOKEN_HOURS)).replace(microsecond=0).isoformat(sep=" ")
    conn.execute(
        """INSERT INTO auth_token (token, account_id, purpose, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (token, account_id, purpose, now, expires),
    )
    return token


def issue_export_token(conn: sqlite3.Connection, account_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = db.now()
    expires = (db.parse(now) + timedelta(minutes=EXPORT_MINUTES)).replace(
        microsecond=0
    ).isoformat(sep=" ")
    conn.execute(
        """INSERT INTO auth_token (token, account_id, purpose, created_at, expires_at)
           VALUES (?, ?, 'export', ?, ?)""",
        (token, account_id, now, expires),
    )
    return token


def consume_token(conn: sqlite3.Connection, token: str, purpose: str) -> int:
    row = conn.execute("SELECT * FROM auth_token WHERE token = ?", (token,)).fetchone()
    if (
        not row
        or row["purpose"] != purpose
        or row["used_at"]
        or row["expires_at"] <= db.now()
    ):
        raise HTTPException(400, "链接无效或过期了，再要一封")
    conn.execute("UPDATE auth_token SET used_at = ? WHERE token = ?", (db.now(), token))
    return int(row["account_id"])


def request_reset(conn: sqlite3.Connection, email: str) -> str | None:
    """邮箱不存在也当成功，免得被人扫号。有账号才发 token。"""
    email = normalize_email(email)
    row = conn.execute("SELECT id FROM account WHERE email = ? AND status = 'active'", (email,)).fetchone()
    if not row:
        return None
    return issue_token(conn, row["id"], "reset")


def reset_password(conn: sqlite3.Connection, token: str, password: str) -> None:
    if len(password) < 8:
        raise HTTPException(400, "密码至少 8 个字符")
    account_id = consume_token(conn, token, "reset")
    conn.execute(
        "UPDATE account SET password_hash = ? WHERE id = ?",
        (hash_password(password), account_id),
    )
    drop_all_sessions(conn, account_id)


def verify_email(conn: sqlite3.Connection, token: str) -> dict:
    account_id = consume_token(conn, token, "verify")
    conn.execute("UPDATE account SET email_verified = 1 WHERE id = ?", (account_id,))
    row = conn.execute("SELECT * FROM account WHERE id = ?", (account_id,)).fetchone()
    return public_account(row)


def link_for(request: Request, purpose: str, token: str) -> str:
    base = (os.environ.get("COFFEEBAR_PUBLIC_URL") or str(request.base_url)).rstrip("/")
    return f"{base}/?{purpose}={token}"


def maybe_send(to: str, subject: str, body: str) -> bool:
    if mail.send(to, subject, body):
        return True
    print(f"[coffeebar] 没配 SMTP，邮件没发出去：{subject} → {to}\n{body}")
    return False


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


def cookie_secure(request: Request | None = None) -> bool:
    if os.environ.get("COFFEEBAR_COOKIE_SECURE") == "1":
        return True
    return bool(request and request.url.scheme == "https")


def set_cookie(response: Response, token: str, request: Request | None = None) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
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
    elif kind == "recipe":
        from . import menu as menu_mod

        assert_owner(menu_mod.recipe_owner(conn, rid), account_id, "没有这个配方")
    else:
        raise HTTPException(400, "锁的资源不对")
