# tests/test_engine.py —— 核心引擎单元测试（独立实例，不污染全局运行态）
import asyncio

import pytest

from engine import ConnectionManager, NeuralWorkflowEngine
from models import ControlAction, WorkflowStatus

NODE_IDS = {
    "node_event_capturer", "node_intent_agent", "node_ui_gen",
    "node_co_agent", "node_dom_renderer",
}


def make_engine() -> NeuralWorkflowEngine:
    return NeuralWorkflowEngine(ws_manager=ConnectionManager())


def run(coro):
    return asyncio.run(coro)


def test_component_library_six_categories_twelve_items():
    eng = make_engine()
    assert len(eng.components) == 12
    categories = {c.category for c in eng.components}
    assert categories == {"触发器", "感知解析", "AI 智能体", "数据逻辑", "前端渲染", "部署"}
    category_en = {c.category_en for c in eng.components}
    assert category_en == {"Triggers", "Perception", "Agents", "Logic", "Frontend", "Deploy"}
    trig = [c for c in eng.components if c.category == "触发器"]
    assert {c.id for c in trig} == {"trig_events", "trig_schedule"}


def test_default_topology_five_nodes_four_edges():
    eng = make_engine()
    assert set(eng.nodes) == NODE_IDS
    assert len(eng.edges) == 4
    edge_pairs = {(e.source, e.target) for e in eng.edges}
    assert ("node_event_capturer", "node_intent_agent") in edge_pairs
    # 意图识别智能体为中枢，向下三路分叉
    assert sum(1 for e in eng.edges if e.source == "node_intent_agent") == 3
    # 每个 DAG 节点都有主题色与非空 JSON 配置
    assert all(n.theme_color.startswith("#") for n in eng.nodes.values())
    assert all(isinstance(n.config_json, dict) and n.config_json for n in eng.nodes.values())


def test_snapshot_shape_initial_state():
    eng = make_engine()
    snap = eng.get_snapshot()
    assert snap.version == "v2.8"
    assert snap.selected_node_id == "node_ui_gen"
    assert len(snap.nodes) == 5
    assert len(snap.edges) == 4
    assert len(snap.telemetry.cpu_history) == 10
    assert len(snap.telemetry.memory_history) == 10
    assert len(snap.telemetry.ecg_waveform) == 10
    assert len(snap.terminal_logs) == 10


def test_append_log_trims_to_50():
    eng = make_engine()

    async def fill():
        for i in range(60):
            await eng.append_log(f"log-{i}")

    run(fill())
    assert len(eng.terminal_logs) == 50
    assert eng.terminal_logs[-1] == "log-59"


def test_control_run_pause_debug_reset_transitions():
    eng = make_engine()
    eng.status = WorkflowStatus.IDLE

    async def scenario():
        await eng.handle_control(ControlAction.PAUSE)
        assert eng.status == WorkflowStatus.PAUSED
        assert not eng._pause_gate.is_set()

        await eng.handle_control(ControlAction.RUN)
        assert eng.status == WorkflowStatus.RUNNING
        assert eng._pause_gate.is_set()
        assert eng._debug_mode is False

        await eng.handle_control(ControlAction.DEBUG)
        assert eng.status == WorkflowStatus.DEBUG
        assert eng._debug_mode is True

        await eng.handle_control(ControlAction.RESET)
        assert eng.status == WorkflowStatus.RUNNING
        assert set(eng.nodes) == NODE_IDS
        assert eng.nodes["node_ui_gen"].progress == 98.6

    run(scenario())


def test_reset_releases_debug_suspension():
    """回归：RESET 必须同时放行单步门，否则调试挂起后工作循环将永久冻结"""
    eng = make_engine()

    async def scenario():
        await eng.handle_control(ControlAction.DEBUG)
        eng._debug_step_gate.clear()  # 模拟循环已消费掉这一步并挂起于下一阶段
        await eng.handle_control(ControlAction.RESET)
        assert eng.status == WorkflowStatus.RUNNING
        assert eng._debug_mode is False
        assert eng._pause_gate.is_set()
        assert eng._debug_step_gate.is_set()
        # 放行后等待函数不再阻塞
        await asyncio.wait_for(eng._wait_if_paused_or_debug("after_reset"), timeout=1.0)

    run(scenario())


def test_debug_step_gate_releases_single_step():
    eng = make_engine()

    async def scenario():
        eng._debug_mode = True
        eng._debug_step_gate.set()  # 模拟 DEBUG 按钮的单步放行
        await asyncio.wait_for(eng._wait_if_paused_or_debug("stage_a"), timeout=1.0)
        # 单步放行后 gate 已被清空，下一个阶段应被挂起
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(eng._wait_if_paused_or_debug("stage_b"), timeout=0.3)

    run(scenario())


def test_pause_gate_blocks_execution():
    eng = make_engine()

    async def scenario():
        eng._pause_gate.clear()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(eng._wait_if_paused_or_debug("stage"), timeout=0.3)
        eng._pause_gate.set()
        await asyncio.wait_for(eng._wait_if_paused_or_debug("stage"), timeout=1.0)

    run(scenario())


def test_simulated_node_execution_latency_and_confidence():
    eng = make_engine()

    async def scenario():
        res = await eng._execute_llm_or_simulate(eng.nodes["node_ui_gen"])
        assert 6 <= res["latency_ms"] <= 15
        assert 98.0 <= res["confidence"] <= 99.9

    run(scenario())


def test_llm_fallback_when_api_unreachable(monkeypatch):
    """配置了 API Key 但外部模型不可达时，应降级为本地神经内核并留下 [Warn] 日志"""
    eng = make_engine()
    monkeypatch.setenv("LLM_API_KEY", "dummy-key")
    monkeypatch.setenv("LLM_API_BASE", "http://127.0.0.1:1")  # 必然连接失败

    async def scenario():
        res = await eng._execute_llm_or_simulate(eng.nodes["node_intent_agent"])
        assert 6 <= res["latency_ms"] <= 15
        assert any("[Warn] 外部模型调用降级为本地神经内核" in line for line in eng.terminal_logs)

    run(scenario())


def test_update_node_config_success_and_missing():
    eng = make_engine()

    async def scenario():
        node = await eng.update_node_config("node_ui_gen", {"role": "patched"})
        assert node.config_json == {"role": "patched"}
        assert eng.selected_node_id == "node_ui_gen"
        with pytest.raises(KeyError):
            await eng.update_node_config("node_ghost", {})

    run(scenario())


def test_connection_manager_broadcast_no_connection_is_noop():
    mgr = ConnectionManager()

    async def scenario():
        await mgr.broadcast("telemetry_tick", {"cpu": 1.0})  # 无连接时不抛错
        assert mgr.active_connections == set()

    run(scenario())
