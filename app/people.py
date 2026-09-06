"""谁喝的：人名标签，不是账号。"""

from __future__ import annotations

import sqlite3

from . import db
from .errors import Conflict


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _row(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


def list_people(
    conn: sqlite3.Connection, include_inactive: bool = False, owner_id: int | None = None
) -> list[dict]:
    """带上每人的记录条数，删人前要拿它提示影响面。"""
    where, args = ["1 = 1"], []
    if not include_inactive:
        where.append("p.active = 1")
    if owner_id is not None:
        where.append("p.owner_id = ?")
        args.append(owner_id)
    return _rows(
        conn.execute(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM consumption_event c
                         WHERE c.person_id = p.id AND c.voided_at IS NULL) AS cups
                FROM person p WHERE {' AND '.join(where)}
                ORDER BY p.active DESC, p.name""",
            args,
        )
    )


def ensure_person(conn: sqlite3.Connection, name: str | None, owner_id: int | None = None) -> int | None:
    """输入即创建。名字为空表示不记是谁。同名只在同一账号下算重复。"""
    if not name or not name.strip():
        return None
    name = name.strip()
    if owner_id is None:
        row = conn.execute(
            "SELECT id FROM person WHERE name = ? AND owner_id IS NULL", (name,)
        ).fetchone()
        if row:
            return int(row[0])
        cur = conn.execute(
            "INSERT INTO person (name, owner_id, created_at) VALUES (?, NULL, ?)",
            (name, db.now()),
        )
        return int(cur.lastrowid)
    conn.execute(
        """INSERT INTO person (name, owner_id, created_at) VALUES (?, ?, ?)
           ON CONFLICT(owner_id, name) DO NOTHING""",
        (name, owner_id, db.now()),
    )
    return int(
        conn.execute(
            "SELECT id FROM person WHERE name = ? AND owner_id = ?", (name, owner_id)
        ).fetchone()[0]
    )


def rename_person(conn: sqlite3.Connection, person_id: int, name: str) -> None:
    """改名只改这一行；历史流水通过外键自动跟着变。"""
    name = name.strip()
    if not name:
        raise Conflict("名字不能为空")
    owner = conn.execute("SELECT owner_id FROM person WHERE id = ?", (person_id,)).fetchone()
    exists = conn.execute(
        "SELECT id FROM person WHERE name = ? AND id <> ? AND owner_id IS ?",
        (name, person_id, owner["owner_id"] if owner else None),
    ).fetchone()
    if exists:
        raise Conflict(f"已经有叫「{name}」的人了")
    conn.execute("UPDATE person SET name = ? WHERE id = ?", (name, person_id))


def set_person_active(conn: sqlite3.Connection, person_id: int, active: bool) -> None:
    """停用是轻量选项：选人列表里不再出现，名字和归属都还在。"""
    conn.execute("UPDATE person SET active = ? WHERE id = ?", (1 if active else 0, person_id))


@db.atomic
def delete_person(conn: sqlite3.Connection, person_id: int) -> dict:
    """真删掉这个人。

    他名下的流水**不删**，只是失去归属变成「没记」——那些克重是真扣过的，
    钱也真花了，删人不该让库存账和统计总数跟着变。想把记录留给别人，先用
    「改归属」挪走再删。
    """
    row = _row(conn.execute("SELECT * FROM person WHERE id = ?", (person_id,)))
    if not row:
        raise Conflict("没有这个人")

    affected = conn.execute(
        "SELECT COUNT(*) FROM consumption_event WHERE person_id = ?", (person_id,)
    ).fetchone()[0]

    ts = db.now()
    if affected:
        conn.executemany(
            """INSERT INTO consumption_audit (cons_id, field, old_value, new_value, at)
               VALUES (?, 'person', ?, NULL, ?)""",
            [
                (r[0], row["name"], ts)
                for r in conn.execute(
                    "SELECT id FROM consumption_event WHERE person_id = ?", (person_id,)
                ).fetchall()
            ],
        )
        conn.execute(
            "UPDATE consumption_event SET person_id = NULL WHERE person_id = ?", (person_id,)
        )
    conn.execute("DELETE FROM person WHERE id = ?", (person_id,))
    return {"name": row["name"], "orphaned": affected}
