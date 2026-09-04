"""写锁：同一条资源同时只有一个写会话。

网页之间是**软锁**——第二处可以提示接管，不用干等超时（单人自用，最常见的
冲突是自己在另一台机器上开着编辑页）。非网页来源（MCP）**硬拒绝**，Agent
不该替人抢锁。见 docs/002「网页侧是软锁：提示接管，不是硬拒绝」。
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from . import db

TIMEOUT = timedelta(minutes=5)      # 无心跳 5 分钟自动过期
HEARTBEAT_HINT = 60                 # 编辑页每 60 秒续一次


class Locked(Exception):
    def __init__(self, holder: str | None, since: str, minutes: float, takeable: bool):
        self.holder = holder or "另一处"
        self.since = since
        self.minutes = minutes
        self.takeable = takeable
        super().__init__(f"{self.holder} 正在编辑（{minutes:.0f} 分钟前）")

    def detail(self) -> dict:
        return {
            "error": "locked",
            "holder": self.holder,
            "since": self.since,
            "minutes_ago": round(self.minutes, 1),
            "can_take_over": self.takeable,
            "message": (
                f"{self.holder}正在编辑这一条（{self.minutes:.0f} 分钟前），要接管吗？"
                if self.takeable
                else f"{self.holder}正在网页里编辑这一条（{self.minutes:.0f} 分钟前），"
                "先去保存或取消，再让我写入。"
            ),
        }


def _expired(heartbeat_at: str) -> bool:
    return (db.parse(db.now()) - db.parse(heartbeat_at)) > TIMEOUT


def acquire(
    conn: sqlite3.Connection,
    resource: str,
    session_id: str,
    holder: str | None = None,
    source: str = "web",
    take_over: bool = False,
) -> dict:
    """拿锁。source='web' 时可 take_over；其他来源遇到活锁一律拒绝。"""
    row = conn.execute("SELECT * FROM write_lock WHERE resource = ?", (resource,)).fetchone()
    ts = db.now()

    if row and row["session_id"] != session_id and not _expired(row["heartbeat_at"]):
        minutes = (db.parse(ts) - db.parse(row["acquired_at"])).total_seconds() / 60
        takeable = source == "web"
        if not (takeable and take_over):
            raise Locked(row["holder"], row["acquired_at"], minutes, takeable)

    conn.execute(
        """INSERT INTO write_lock (resource, session_id, holder, acquired_at, heartbeat_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(resource) DO UPDATE
             SET session_id = ?, holder = ?, acquired_at = ?, heartbeat_at = ?""",
        (resource, session_id, holder, ts, ts, session_id, holder, ts, ts),
    )
    return {"resource": resource, "session_id": session_id, "heartbeat_seconds": HEARTBEAT_HINT}


def heartbeat(conn: sqlite3.Connection, resource: str, session_id: str) -> bool:
    """续锁。返回 False 表示锁已经不是自己的了（被接管或已过期）。"""
    row = conn.execute("SELECT * FROM write_lock WHERE resource = ?", (resource,)).fetchone()
    if not row or row["session_id"] != session_id:
        return False
    conn.execute(
        "UPDATE write_lock SET heartbeat_at = ? WHERE resource = ? AND session_id = ?",
        (db.now(), resource, session_id),
    )
    return True


def release(conn: sqlite3.Connection, resource: str, session_id: str) -> None:
    conn.execute(
        "DELETE FROM write_lock WHERE resource = ? AND session_id = ?", (resource, session_id)
    )


def check(conn: sqlite3.Connection, resource: str, session_id: str, source: str = "web") -> None:
    """写操作前校验：别人正持有活锁就抛 Locked。"""
    row = conn.execute("SELECT * FROM write_lock WHERE resource = ?", (resource,)).fetchone()
    if not row or row["session_id"] == session_id or _expired(row["heartbeat_at"]):
        return
    minutes = (db.parse(db.now()) - db.parse(row["acquired_at"])).total_seconds() / 60
    raise Locked(row["holder"], row["acquired_at"], minutes, source == "web")


def status(conn: sqlite3.Connection, resource: str) -> dict | None:
    row = conn.execute("SELECT * FROM write_lock WHERE resource = ?", (resource,)).fetchone()
    if not row or _expired(row["heartbeat_at"]):
        return None
    return dict(row)
