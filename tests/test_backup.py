import sqlite3
from pathlib import Path

from app import backup, store


def test_pack_and_restore_roundtrip(conn, tmp_path, monkeypatch):
    store.create_bean(conn, {"name": "备份豆"})
    conn.close()
    from app import db as db_mod

    src = Path(db_mod.DATA_DIR)
    dest_dir = tmp_path / "out"
    zip_path, local = backup.pack(dest_dir, src)
    assert zip_path.is_file()
    assert zip_path.stat().st_size > 22

    restored = tmp_path / "restored"
    backup.extract_zip(zip_path, restored)
    c = sqlite3.connect(restored / "coffeebar.db")
    names = [r[0] for r in c.execute("SELECT name FROM bean")]
    c.close()
    assert "备份豆" in names


def test_prune_keeps_fourteen(tmp_path):
    folder = tmp_path / "b"
    folder.mkdir()
    for i in range(16):
        p = folder / f"coffeebar-2026-01-{i + 1:02d}-0000.zip"
        p.write_bytes(b"x" * 30)
        # 保证 mtime 有先后
        import os
        import time

        os.utime(p, (time.time() + i, time.time() + i))
    dropped = backup.prune(folder, keep=14)
    assert len(dropped) == 2
    assert len(list(folder.glob("coffeebar-*.zip"))) == 14
