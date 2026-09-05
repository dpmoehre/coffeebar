"""SQLite 连接与建表。单文件、无 ORM。"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 运行数据只在本机，不入库（.gitignore 已排除 data/）
DATA_DIR = Path(os.environ.get("COFFEEBAR_DATA", Path(__file__).resolve().parent.parent / "data"))
PHOTO_DIR = DATA_DIR / "photos"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"

# 一天以凌晨 4 点分界：晚上开的酒喝到凌晨算前一天
DAY_CUTOFF_HOURS = 4


def db_path() -> Path:
    return DATA_DIR / "coffeebar.db"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False：同步路由跑在线程池里，建连接和关连接可能不在同一个
    # 线程。每个请求独占一个连接、不共享，所以放开这个检查是安全的。
    conn = sqlite3.connect(db_path(), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 4000")  # 写撞上了就等一会，别直接报 locked
    return conn


# 给已经建好的库补列。CREATE TABLE IF NOT EXISTS 不会动已存在的表，
# 所以加字段要在这里登记一条，老库下次启动自动补上。
ADDED_COLUMNS = [
    ("bean", "varietal", "TEXT"),
    ("bean", "producer", "TEXT"),
    ("bean", "altitude", "TEXT"),
    ("brew_guide", "note", "TEXT"),
    ("bottle", "kind", "TEXT"),
]


# 放宽 CHECK 用的：SQLite 改不了 CHECK，只能照 schema.sql 重建表再把数据搬过去。
# key 是表名，值是「老库 DDL 里有这段就说明该重建了」。
STALE_CHECKS = {
    "bean_photo": "kind IN ('pack', 'tray')",
    # 老库 lot_id 非空且只指向 bean_lot，酒进同一张消耗表得放宽
    "consumption_event": "lot_id       INTEGER NOT NULL REFERENCES bean_lot",
}


def _rebuild(conn: sqlite3.Connection, table: str) -> None:
    """按 schema.sql 重建单表并搬数据（交集列）。"""
    ddl = next(
        s for s in SCHEMA.read_text(encoding="utf-8").split(";")
        if f"CREATE TABLE IF NOT EXISTS {table}" in s
    )
    old = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(f"ALTER TABLE {table} RENAME TO _old_{table}")
        conn.executescript(ddl + ";")
        keep = [c for c in (r[1] for r in conn.execute(f"PRAGMA table_info({table})")) if c in old]
        cols = ", ".join(keep)
        conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _old_{table}")
        conn.execute(f"DROP TABLE _old_{table}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    for table, column, decl in ADDED_COLUMNS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    for table, stale in STALE_CHECKS.items():
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if row and stale in row["sql"]:
            _rebuild(conn, table)
    # 重建表会带走旧索引；schema 再跑一遍把 IF NOT EXISTS 的索引补上
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    # 新列上的索引不能写进 schema.sql 的第一遍执行——老库还没重建时列不存在
    cols = {r[1] for r in conn.execute("PRAGMA table_info(consumption_event)")}
    if "bottle_lot_id" in cols:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cons_blot ON consumption_event(bottle_lot_id)"
        )


def now() -> str:
    """本地时间的 ISO 字符串。单机自用，不做多时区。"""
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def business_day(ts: str | datetime) -> str:
    """业务日：凌晨 4 点前算前一天。"""
    dt = parse(ts) if isinstance(ts, str) else ts
    return (dt - timedelta(hours=DAY_CUTOFF_HOURS)).date().isoformat()


def period_start(period: str, ref: datetime | None = None) -> str | None:
    """统计期间的起点（含）。返回 None 表示不限（全部）。"""
    ref = ref or datetime.now()
    base = (ref - timedelta(hours=DAY_CUTOFF_HOURS)).date()
    if period == "week":
        start = base - timedelta(days=base.weekday())
    elif period == "month":
        start = base.replace(day=1)
    elif period == "year":
        start = base.replace(month=1, day=1)
    else:
        return None
    # 业务日 D 的实际起点是 D 的 04:00
    return datetime.combine(start, datetime.min.time()).replace(
        hour=DAY_CUTOFF_HOURS
    ).isoformat(sep=" ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
