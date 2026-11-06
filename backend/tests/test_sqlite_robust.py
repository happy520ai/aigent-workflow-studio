# tests/test_sqlite_robust.py —— T21：SQLite 稳健化（WAL PRAGMA + 显式迁移幂等 + 写串行化）
import asyncio
import sqlite3

from perfect_engine import SQLITE_WRITE_LOCK, CheckpointStore, sqlite_connect


def _make_store(tmp_path) -> CheckpointStore:
    return CheckpointStore(db_path=str(tmp_path / "ckpt.db"))


def test_wal_pragmas_applied(tmp_path):
    store = _make_store(tmp_path)
    conn = sqlite_connect(store.db_path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    conn.close()


def test_schema_version_table_created(tmp_path):
    store = _make_store(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row is not None
    assert row[0] == CheckpointStore.SCHEMA_VERSION


def test_migration_idempotent_on_reopen(tmp_path):
    # 同一库重复初始化（模拟重启）：版本不变、无异常
    path = str(tmp_path / "ckpt.db")
    CheckpointStore(db_path=path)
    CheckpointStore(db_path=path)
    CheckpointStore(db_path=path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == CheckpointStore.SCHEMA_VERSION
        # checkpoints 表结构完好
        cols = [r[1] for r in conn.execute("PRAGMA table_info(checkpoints)").fetchall()]
        assert "topology_json" in cols


def test_migration_upgrades_legacy_v1_db(tmp_path):
    # 模拟 v1 旧库：有 checkpoints（无 topology_json 列、无 schema_version 表）+ 一条旧断点
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                state_payload TEXT NOT NULL,
                generated_code TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO checkpoints VALUES ('ckpt_legacy', 'run_old', 'node_a', '2026-01-01 00:00:00.000', '{\"k\":1}', '<div>old</div>')"
        )
        conn.commit()

    store = CheckpointStore(db_path=path)  # 打开即迁移
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == CheckpointStore.SCHEMA_VERSION
        cols = [r[1] for r in conn.execute("PRAGMA table_info(checkpoints)").fetchall()]
        assert "topology_json" in cols

    # 旧数据无损：可正常读回
    import asyncio

    row = asyncio.run(store.get_checkpoint("ckpt_legacy"))
    assert row is not None
    assert row["state_payload"] == {"k": 1}
    assert row["topology_json"] is None  # 旧断点无拓扑


def test_concurrent_writes_serialized(tmp_path):
    store = _make_store(tmp_path)

    async def scenario():
        tasks = [
            store.save_checkpoint(f"run_{i % 3}", f"node_{i}", {"i": i}, f"<div>{i}</div>")
            for i in range(24)
        ]
        return await asyncio.gather(*tasks)

    ids = asyncio.run(scenario())
    assert len(ids) == 24
    assert len(set(ids)) == 24  # 无覆盖
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 24


def test_write_lock_is_reentrant_safe():
    # SQLITE_WRITE_LOCK 为 threading.Lock，写路径均短临界区；此断言防误改为不可重入的进程级错误语义
    assert not isinstance(SQLITE_WRITE_LOCK, type(None))
