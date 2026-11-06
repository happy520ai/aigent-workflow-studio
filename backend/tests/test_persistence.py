# tests/test_persistence.py —— A7：拓扑持久化 / 断点剪枝 / 旧库迁移 / restore 还原拓扑
import asyncio
import sqlite3

from models import ControlAction
from perfect_engine import CheckpointStore, ConnectionManager, PerfectNeuralEngine


def run(coro):
    return asyncio.run(coro)


def test_topology_roundtrip_and_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("AIGENT_DB_PATH", str(tmp_path / "p.db"))
    eng = PerfectNeuralEngine(ws_manager=ConnectionManager(), persist_topology=True)
    assert len(eng.nodes) == 5

    # 增节点（内部触发 save_topology）
    node = run(eng.add_custom_node_from_sidebar("dep_publish", 700, 300))
    assert len(eng.nodes) == 6

    # 新建引擎从 SQLite 还原
    eng2 = PerfectNeuralEngine(ws_manager=ConnectionManager(), persist_topology=True)
    assert len(eng2.nodes) == 6
    assert node.id in eng2.nodes

    # RESET 回默认并落库
    run(eng2.handle_control(ControlAction.RESET))
    eng3 = PerfectNeuralEngine(ws_manager=ConnectionManager(), persist_topology=True)
    assert len(eng3.nodes) == 5
    assert len(eng3.edges) == 4


def test_persist_disabled_keeps_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AIGENT_DB_PATH", str(tmp_path / "off.db"))
    eng = PerfectNeuralEngine(ws_manager=ConnectionManager(), persist_topology=True)
    run(eng.add_custom_node_from_sidebar("dep_publish", 700, 300))

    # persist_topology=False 的引擎不读库，仍是默认 5 节点
    eng_off = PerfectNeuralEngine(ws_manager=ConnectionManager(), persist_topology=False)
    assert len(eng_off.nodes) == 5


def test_checkpoint_pruning_to_max(tmp_path, monkeypatch):
    monkeypatch.setenv("AIGENT_DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setattr(CheckpointStore, "CHECKPOINT_MAX", 5, raising=False)

    store = CheckpointStore()
    for i in range(8):
        run(store.save_checkpoint("run", f"node_{i}", {"i": i}, "<div/>"))

    rows = run(store.list_checkpoints(limit=20))
    assert len(rows) == 5
    # 保留的是最近 5 条
    kept_nodes = {r["node_id"] for r in rows}
    assert kept_nodes == {"node_3", "node_4", "node_5", "node_6", "node_7"}


def test_old_ddl_database_migrated_losslessly(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        # 按旧 DDL 建表（无 topology_json 列）并写入旧数据
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
            "INSERT INTO checkpoints VALUES ('old1','r','n','2020-01-01 00:00:00.000','{}','<div/>')"
        )
        conn.commit()

    store = CheckpointStore(db_path=str(db))
    rows = run(store.list_checkpoints(limit=10))
    # 旧数据无损
    assert len(rows) == 1
    assert rows[0]["checkpoint_id"] == "old1"
    # list 键集合保持原有 6 个（不暴露 topology_json）
    assert set(rows[0]) == {
        "checkpoint_id", "run_id", "node_id", "timestamp", "state_payload", "generated_code",
    }
    # get_checkpoint 返回完整行（含拓扑）
    ck = run(store.get_checkpoint("old1"))
    assert ck["topology_json"] is None
    assert ck["generated_code"] == "<div/>"


def test_get_checkpoint_returns_topology(tmp_path, monkeypatch):
    monkeypatch.setenv("AIGENT_DB_PATH", str(tmp_path / "p.db"))
    eng = PerfectNeuralEngine(ws_manager=ConnectionManager(), persist_topology=True)
    topo = {
        "nodes": [n.model_dump() for n in eng.nodes.values()],
        "edges": [e.model_dump() for e in eng.edges],
    }
    cid = run(
        eng.checkpoint_store.save_checkpoint(
            "run_t", "node_ui_gen", {"k": 1}, "<div/>", topology=topo
        )
    )
    ck = run(eng.checkpoint_store.get_checkpoint(cid))
    assert ck["topology_json"] is not None
    assert len(ck["topology_json"]["nodes"]) == 5


def test_restore_restores_topology(perfect_client):
    from perfect_main import engine

    # 全局引擎上先加节点并把当前拓扑随断点入库
    node = run(engine.add_custom_node_from_sidebar("dep_publish", 700, 300))
    topo = {
        "nodes": [n.model_dump() for n in engine.nodes.values()],
        "edges": [e.model_dump() for e in engine.edges],
    }
    cid = run(
        engine.checkpoint_store.save_checkpoint(
            "run_restore", "node_ui_gen", {"k": 1}, "<div/>", topology=topo
        )
    )
    try:
        # RESET 回默认 5 节点
        run(engine.handle_control(ControlAction.RESET))
        snap = perfect_client.get("/api/v1/workflow").json()
        assert len(snap["nodes"]) == 5

        # restore 断点 → 节点与连线随断点还原
        r = perfect_client.post(f"/api/v1/checkpoints/{cid}/restore")
        assert r.status_code == 200
        snap = perfect_client.get("/api/v1/workflow").json()
        assert any(n["id"] == node.id for n in snap["nodes"])
        assert any(e["target"] == node.id for e in snap["edges"])
    finally:
        # 清理全局状态，不给后续测试留脏拓扑
        run(engine.handle_control(ControlAction.RESET))
