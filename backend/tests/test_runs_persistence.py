# tests/test_runs_persistence.py —— T26：运行记录持久化（重启不丢）
import asyncio
import time

from perfect_engine import CheckpointStore, ConnectionManager, PerfectNeuralEngine


def run(coro):
    return asyncio.run(coro)


def test_runs_roundtrip_order_and_fields(tmp_path):
    store = CheckpointStore(db_path=str(tmp_path / "r.db"))
    run(
        store.save_run("r1", "run_a", "2026-01-01T00:00:00", "2026-01-01T00:00:01", "completed", [{"id": "n1", "status": "success"}])
    )
    run(
        store.save_run("r2", "run_a", "2026-01-01T00:00:02", "2026-01-01T00:00:03", "completed", [])
    )
    rows = run(store.list_runs(limit=10))
    assert [r["round_id"] for r in rows] == ["r2", "r1"]  # 倒序
    assert rows[1]["nodes"][0]["status"] == "success"
    assert rows[0]["status"] == "completed"


def test_runs_survive_reopen(tmp_path):
    path = str(tmp_path / "r.db")
    store = CheckpointStore(db_path=path)
    run(store.save_run("r9", "run_x", "s", "f", "completed", [{"id": "n", "status": "success"}]))
    # 模拟重启：全新实例读同一库
    store2 = CheckpointStore(db_path=path)
    rows = run(store2.list_runs(limit=10))
    assert len(rows) == 1
    assert rows[0]["round_id"] == "r9"


def test_engine_round_persists_to_db(tmp_path, monkeypatch):
    db = str(tmp_path / "eng.db")
    monkeypatch.setenv("AIGENT_DB_PATH", db)
    eng = PerfectNeuralEngine(ws_manager=ConnectionManager())
    run(eng._run_dag_round())
    reader = CheckpointStore(db_path=db)
    rows = run(reader.list_runs(limit=5))
    assert len(rows) >= 1
    assert rows[0]["round_id"] == eng.run_history[-1]["round_id"]


def test_api_runs_reads_from_db(perfect_client, tmp_path):
    from perfect_main import engine

    # 等待至少一轮完整归档（同 test_error_isolation 的时序等待）
    deadline = time.time() + 15
    while time.time() < deadline and not engine.run_history:
        time.sleep(0.3)
    r = perfect_client.get("/api/v1/runs?limit=5")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    # 行结构含 T26 新字段且兼容旧字段
    assert {"round_id", "started_at", "finished_at", "nodes", "run_id", "status"} <= set(rows[0])
