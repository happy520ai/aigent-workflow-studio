# tests/test_error_isolation.py —— A4：单节点错误隔离（error/skipped/兄弟正常）+ run_history + GET /runs
import asyncio

import pytest
from starlette.testclient import TestClient

import operator_registry
from models import NeuralEdge
from perfect_engine import ConnectionManager, PerfectNeuralEngine


def run(coro):
    return asyncio.run(coro)


def make_engine() -> PerfectNeuralEngine:
    return PerfectNeuralEngine(ws_manager=ConnectionManager())


def test_error_isolation_skips_downstream_keeps_sibling(monkeypatch):
    eng = make_engine()
    # 造双根拓扑：event_capturer 与 dom_renderer 为同层兄弟根，intent_agent 只依赖 event
    eng.edges = [
        NeuralEdge(id="e_iso_1", source="node_event_capturer", target="node_intent_agent"),
    ]

    async def boom(cfg, bus):
        raise RuntimeError("算子爆炸")

    # _handlers 在构造时已绑定方法引用，必须替换字典条目才能生效
    monkeypatch.setitem(eng.operator_registry._handlers, "trig_events", boom)

    async def scenario():
        await eng._run_dag_round()

    run(scenario())

    # 失败节点：error + last_error 留痕
    assert eng.nodes["node_event_capturer"].status == "error"
    assert "算子爆炸" in (eng.nodes["node_event_capturer"].last_error or "")
    # 下游：skipped 且未执行
    assert eng.nodes["node_intent_agent"].status == "skipped"
    # 同层兄弟：正常执行成功
    assert eng.nodes["node_dom_renderer"].status == "success"

    # run_history 追加了一轮完整记录
    assert len(eng.run_history) == 1
    record = eng.run_history[0]
    assert record["round_id"].startswith(eng.current_run_id)
    statuses = {n["id"]: n["status"] for n in record["nodes"]}
    assert statuses["node_event_capturer"] == "error"
    assert statuses["node_intent_agent"] == "skipped"
    assert statuses["node_dom_renderer"] == "success"


def test_error_recovery_next_round(monkeypatch):
    eng = make_engine()

    async def boom(cfg, bus):
        raise RuntimeError("瞬时故障")

    async def ok(cfg, bus):
        return {"status": "triggered", "confidence": 99.8, "output": {"ok": True}}

    monkeypatch.setitem(eng.operator_registry._handlers, "trig_events", boom)

    async def scenario():
        await eng._run_dag_round()  # 第一轮：error + 下游 skipped
        monkeypatch.setitem(eng.operator_registry._handlers, "trig_events", ok)
        await eng._run_dag_round()  # 第二轮：恢复正常

    run(scenario())
    assert eng.nodes["node_event_capturer"].status == "success"
    assert eng.nodes["node_intent_agent"].status == "success"
    assert len(eng.run_history) == 2


def test_runs_endpoint_returns_desc_order(perfect_client):
    import time as _time

    from perfect_main import engine

    # 等待至少一轮完整 DAG 归档：轮周期 ~2.5s，且前序用例的快速 lifespan 会把在途轮
    # 中止在 run_history 追加之前（T21/T25 生命周期变更后暴露的时序依赖，此处显式等待）。
    deadline = _time.time() + 15
    while _time.time() < deadline and not engine.run_history:
        _time.sleep(0.3)
    expected_latest = engine.run_history[-1]["round_id"]
    resp = perfect_client.get("/api/v1/runs?limit=20")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert len(rows) >= 1
    # 倒序：第一条应为请求时刻的最新一轮（允许期间插入了更新的轮次）
    assert rows[0]["round_id"] in {expected_latest, engine.run_history[-1]["round_id"]}

