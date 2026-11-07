# tests/test_backup_restore.py —— T64：备份 → 清库 → 恢复 → 断点数一致
# 走子进程边界：Windows 上 sqlite 连接句柄会锁住库文件，子进程退出即释放。
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
BACKUP_SCRIPT = BACKEND_DIR.parent / "scripts" / "backup.py"


def _run(code: str) -> None:
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(BACKEND_DIR))
    assert r.returncode == 0, f"seed/verify 子进程失败:\n{r.stdout}\n{r.stderr}"


def test_backup_restore_roundtrip(tmp_path):
    db = tmp_path / "t64.db"
    out = tmp_path / "backups"

    _run(
        f"""
import asyncio, sys
sys.path.insert(0, r"{BACKEND_DIR}")
from perfect_engine import CheckpointStore

async def seed():
    s = CheckpointStore(db_path=r"{db}")
    for i in range(3):
        await s.save_checkpoint("run_t64", f"node_{{i}}", {{"i": i}}, f"<div>{{i}}</div>")

asyncio.run(seed())
"""
    )

    _conn = sqlite3.connect(str(db))
    count_before = _conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    _conn.close()  # Windows：显式关句柄，否则 unlink 撞锁
    assert count_before == 3

    r = subprocess.run(
        [sys.executable, str(BACKUP_SCRIPT), "--db", str(db), "--out", str(out), "--keep", "7"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    backups = sorted(out.glob("aigent-*.db"))
    assert len(backups) == 1

    # 清库（模拟损坏/误删）——seed 子进程已退出，文件无锁
    db.unlink()
    import shutil

    shutil.copy(backups[0], db)

    _conn = sqlite3.connect(str(db))
    count_after = _conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    _conn.close()
    assert count_after == 3

    _run(
        f"""
import asyncio, sys
sys.path.insert(0, r"{BACKEND_DIR}")
from perfect_engine import CheckpointStore

async def main():
    s = CheckpointStore(db_path=r"{db}")
    rows = await s.list_checkpoints(limit=10)
    assert len(rows) == 3, rows
    assert rows[0]["state_payload"]["i"] in (0, 1, 2)

asyncio.run(main())
"""
    )


def test_backup_keep_prunes_old(tmp_path):
    db = tmp_path / "t64b.db"
    out = tmp_path / "backups"
    # 真库：backup.py 对非 SQLite 文件应报错（此处必须是合法库）
    _conn = sqlite3.connect(str(db))
    _conn.execute("CREATE TABLE checkpoints (checkpoint_id TEXT PRIMARY KEY)")
    _conn.commit()
    _conn.close()

    for _ in range(9):
        r = subprocess.run(
            [sys.executable, str(BACKUP_SCRIPT), "--db", str(db), "--out", str(out), "--keep", "3"],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr

    backups = sorted(out.glob("aigent-*.db"))
    assert len(backups) == 3  # 保留最近 3 份
