# tests/test_perfect_engine.py —— 完美引擎（动态拓扑/SQLite断点/沙盒编译）单元测试（独立实例）
import asyncio
import os

import pytest

from models import ControlAction, NeuralEdge, WorkflowStatus
from perfect_engine import CheckpointStore, ConnectionManager, PerfectNeuralEngine

NODE_IDS = {
    "node_event_capturer", "node_intent_agent", "node_ui_gen",
    "node_co_agent", "node_dom_renderer",
}


def teardown_module(module):
    # 引擎默认在 cwd 落 aigent_checkpoints.db（CheckpointStore 1:1 默认参数），测完清理
    db = os.path.join(os.getcwd(), "aigent_checkpoints.db")
    if os.path.exists(db):
        try:
            os.remove(db)
        except OSError:
            pass
    # 重建同 schema 的 checkpoints 表（与 bootstrap_studio.py 一致），
    # 兼容根目录 test_workflow_e2e.py::test_04 对该库的依赖
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                state_payload TEXT NOT NULL,
                generated_code TEXT NOT NULL
            )
            """
        )
        conn.commit()


def make_engine() -> PerfectNeuralEngine:
    return PerfectNeuralEngine(ws_manager=ConnectionManager())


def run(coro):
    return asyncio.run(coro)


def test_checkpoint_store_roundtrip(tmp_path):
    store = CheckpointStore(db_path=str(tmp_path / "ckpt.db"))

    async def scenario():
        cid = await store.save_checkpoint("run_x", "node_ui_gen", {"k": "v", "n": 1}, "<div>code</div>")
        await store.save_checkpoint("run_x", "node_event_capturer", {}, "code2")
        rows = await store.list_checkpoints(limit=10)
        return cid, rows

    cid, rows = run(scenario())
    assert cid.startswith("ckpt_")
    assert len(rows) == 2
    top = next(r for r in rows if r["checkpoint_id"] == cid)
    assert top["node_id"] == "node_ui_gen"
    assert top["run_id"] == "run_x"
    assert top["state_payload"] == {"k": "v", "n": 1}
    assert top["generated_code"] == "<div>code</div>"
    assert "timestamp" in top


def test_compile_topological_layers_three_layers():
    eng = make_engine()
    layers = eng.compile_topological_layers()
    assert len(layers) == 3
    assert layers[0] == ["node_event_capturer"]
    assert layers[1] == ["node_intent_agent"]
    assert set(layers[2]) == {"node_ui_gen", "node_co_agent", "node_dom_renderer"}
    flat = [nid for layer in layers for nid in layer]
    assert sorted(flat) == sorted(NODE_IDS)


def test_compile_topological_layers_handles_cycle():
    eng = make_engine()
    # 人为造全环：event -> intent -> ui_gen -> event（Cyclic Agent Graph）
    eng.edges.append(NeuralEdge(id="edge_cycle", source="node_ui_gen", target="node_event_capturer"))
    layers = eng.compile_topological_layers()
    flat = [nid for layer in layers for nid in layer]
    assert sorted(flat) == sorted(NODE_IDS)  # 环上节点作为反馈层兜底，不丢失
    # 全环时无任何入度为零的起点，按文档设计整体落入单个反馈层
    assert len(layers) == 1
    assert set(layers[0]) == NODE_IDS


def test_shared_memory_bus_initial_state():
    eng = make_engine()
    assert set(eng.shared_memory_bus) == {
        "last_event", "intent", "co_agent_review", "dom_hydration_status",
    }
    assert eng.shared_memory_bus["dom_hydration_status"] == "READY"
    assert eng.shared_memory_bus["co_agent_review"] == "PASS_WITH_99.2%_CONFIDENCE"


def test_default_sandbox_template_contains_telemetry_cards():
    eng = make_engine()
    html = eng._default_sandbox_template("测试标题ABC")
    assert "DOM RENDERER LIVE SANDBOX" in html
    assert "测试标题ABC" in html
    assert "突触延迟" in html
    assert "98.6%" in html
    assert "Hydrated @" in html


def test_execute_single_node_updates_memory_bus_sandbox_and_checkpoint():
    eng = make_engine()
    node = eng.nodes["node_ui_gen"]
    before_html = eng.latest_sandbox_html

    async def scenario():
        await eng._execute_single_node(node)

    run(scenario())
    # A3 后指标为真实测量：成功即 progress=100 / status=success，置信度取算子返回值
    assert node.progress == 100.0
    assert node.confidence == 98.6  # agent_codegen（ui_generation 别名）算子返回的置信度
    assert node.status == "success"
    assert node.latency_ms >= 1  # 真实毫秒，不再夹逼 6~14
    # ui_generation 节点触发沙盒代码重新编译
    assert eng.latest_sandbox_html != before_html
    assert "DOM RENDERER LIVE SANDBOX" in eng.latest_sandbox_html
    # 共享记忆总线写入
    entry = eng.shared_memory_bus["node_ui_gen"]
    assert entry["confidence"] == 98.6
    assert "updated_at" in entry
    # SQLite 断点已持久化
    rows = run(eng.checkpoint_store.list_checkpoints(limit=5))
    assert any(r["node_id"] == "node_ui_gen" for r in rows)


def test_debug_single_step_gate_semantics():
    eng = make_engine()

    async def scenario():
        eng._debug_mode = True
        eng._debug_step_gate.set()
        await asyncio.wait_for(
            eng._execute_single_node(eng.nodes["node_event_capturer"]), timeout=3.0
        )
        assert eng.nodes["node_event_capturer"].progress == 100.0
        # 单步已消费（gate 被 clear），下一个节点应挂起
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                eng._execute_single_node(eng.nodes["node_intent_agent"]), timeout=0.6
            )

    run(scenario())


def test_add_custom_node_from_sidebar_and_topology_recompile():
    eng = make_engine()

    async def scenario():
        return await eng.add_custom_node_from_sidebar("dep_publish", 700.0, 300.0)

    node = run(scenario())
    assert node.id.startswith("node_dep_publish_")
    assert node.title == "发布"
    assert node.theme_color == "#ec4899"
    assert node.id in eng.nodes
    new_edges = [e for e in eng.edges if e.target == node.id]
    assert len(new_edges) == 1
    assert new_edges[0].source == "node_intent_agent"
    # 拓扑自动重编译仍覆盖全部节点（新节点纳入并行调度层）
    layers = eng.compile_topological_layers()
    flat = [nid for layer in layers for nid in layer]
    assert node.id in flat
    with pytest.raises(ValueError):
        run(eng.add_custom_node_from_sidebar("nope_xyz", 0, 0))


def test_handle_control_transitions_and_reset_restores_topology():
    eng = make_engine()
    eng.status = WorkflowStatus.IDLE
    old_run = eng.current_run_id

    async def scenario():
        await eng.handle_control(ControlAction.PAUSE)
        assert eng.status == WorkflowStatus.PAUSED
        assert not eng._pause_gate.is_set()

        await eng.handle_control(ControlAction.RUN)
        assert eng.status == WorkflowStatus.RUNNING
        assert eng._pause_gate.is_set()

        await eng.handle_control(ControlAction.DEBUG)
        assert eng.status == WorkflowStatus.DEBUG
        eng._debug_step_gate.clear()  # 模拟循环消费掉这一步并挂起于下一阶段

        # 篡改拓扑后 RESET 应完整复原节点与连线
        eng.nodes["node_ui_gen"].config_json = {"patched": True}
        eng.nodes["node_extra"] = eng.nodes["node_ui_gen"].model_copy(update={"id": "node_extra"})

        await eng.handle_control(ControlAction.RESET)
        assert eng.status == WorkflowStatus.RUNNING
        assert eng._debug_mode is False
        assert eng._pause_gate.is_set()
        # 回归：RESET 必须放行单步门，否则调试挂起后工作循环永久冻结
        assert eng._debug_step_gate.is_set()
        assert eng.current_run_id != old_run
        assert set(eng.nodes) == NODE_IDS
        assert len(eng.edges) == 4
        assert eng.nodes["node_ui_gen"].config_json.get("name") == "Agentinightik.eod"

    run(scenario())
