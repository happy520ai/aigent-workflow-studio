# tests/test_metrics.py —— T23：Prometheus 指标端点与打点
import time

import pytest
from starlette.testclient import TestClient

from metrics import MetricsRegistry
from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def test_registry_render_parse():
    reg = MetricsRegistry()
    reg.observe_node("ui_generation", "success", 42)
    reg.observe_node("ui_generation", "error", 12)
    reg.observe_llm("success")
    reg.observe_llm("degraded")
    reg.observe_round(120.0)
    reg.observe_round(30.0)
    text = reg.render(ws_connections=2)
    # Prometheus 文本基础结构
    assert "# TYPE aigent_node_exec_total counter" in text
    assert 'aigent_node_exec_total{node_type="ui_generation",status="success"} 1' in text
    assert 'aigent_llm_calls_total{outcome="degraded"} 1' in text
    # 直方图：le 桶单调不减、count=样本数、sum 正确
    assert 'aigent_dag_round_duration_ms_bucket{le="250"} 2' in text
    assert 'aigent_dag_round_duration_ms_bucket{le="+Inf"} 2' in text
    assert "aigent_dag_round_duration_ms_count 2" in text
    assert "aigent_dag_round_duration_ms_sum 150.000" in text
    assert "aigent_ws_connections 2" in text


def test_metrics_endpoint_content_type_and_body(api):
    r = api.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert body.startswith("# HELP")
    assert "aigent_dag_round_duration_ms_bucket" in body
    assert "aigent_ws_connections 0" in body


def test_metrics_endpoint_requires_token_when_configured(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "tok-metrics-1")
    # /metrics 属敏感面：配置令牌后无头 401，即使 PUBLIC_READ=1 也不放行
    monkeypatch.setenv("AIGENT_PUBLIC_READ", "1")
    assert api.get("/metrics").status_code == 401
    r = api.get("/metrics", headers={"X-Admin-Token": "tok-metrics-1"})
    assert r.status_code == 200


def test_metrics_reflect_live_engine_rounds(api):
    # 会话客户端已让引擎跑过若干轮：节点计数与轮次直方图应有真实数据
    deadline = time.time() + 15
    body = ""
    while time.time() < deadline:
        body = api.get("/metrics").text
        if "aigent_dag_round_duration_ms_count 0" not in body:
            break
        time.sleep(0.3)
    assert 'aigent_node_exec_total{node_type="ui_generation",status="success"}' in body
    count_line = next(
        ln for ln in body.splitlines() if ln.startswith("aigent_dag_round_duration_ms_count")
    )
    assert int(count_line.split()[-1]) >= 1


def test_llm_degrade_counters_via_engine(monkeypatch):
    from perfect_engine import ConnectionManager, PerfectNeuralEngine

    eng = PerfectNeuralEngine(ws_manager=ConnectionManager())
    eng.llm_config = {"api_key": "sk-unit", "api_base": "https://unit.example/v1", "model": "m"}

    async def rebinding(api_base: str, allow_private: bool = False) -> str:
        raise ValueError("rejected by test")

    import perfect_engine as pe

    monkeypatch.setattr(pe, "resolve_and_pin_api_base", rebinding)
    from metrics import metrics as reg

    before_fail = None
    import re as _re

    text = reg.render()
    m = _re.search(r'aigent_llm_calls_total\{outcome="failure"\} (\d+)', text)
    before_fail = int(m.group(1))

    import asyncio

    asyncio.run(eng._execute_single_node(eng.nodes["node_ui_gen"]))

    text2 = reg.render()
    m2 = _re.search(r'aigent_llm_calls_total\{outcome="failure"\} (\d+)', text2)
    assert int(m2.group(1)) == before_fail + 1
    assert 'aigent_llm_calls_total{outcome="degraded"}' in text2
