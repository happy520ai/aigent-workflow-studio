# tests/test_limits.py —— T13：限流与体积限制
# 覆盖：严格面限流 429（settings PUT）、ast code 512KB 413、config_json 64KB 413、
#       节点/连线上限 413。限流测试直接收紧 strict_limiter 容量后恢复。
import pytest
from starlette.testclient import TestClient

import perfect_main
from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def test_strict_rate_limit_429(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("LLM_API_BASE_ALLOWLIST", "")
    payload = {"api_key": "", "api_base": "http://169.254.169.254/", "model": "m"}
    limiter = perfect_main.strict_limiter
    old_capacity, old_rate = limiter.capacity, limiter.rate_per_min
    try:
        limiter.capacity = 2
        limiter.rate_per_min = 0  # 关闭补给：只受突发容量约束（rate=600 会随请求间隔恰好补满）
        limiter._buckets.clear()
        # 前两个请求正常到达路由（SSRF 校验返回 400），第三个被限流 429
        assert api.put("/api/v1/settings/llm", json=payload).status_code == 400
        assert api.put("/api/v1/settings/llm", json=payload).status_code == 400
        r = api.put("/api/v1/settings/llm", json=payload)
        assert r.status_code == 429
        assert "Retry-After" in r.headers
    finally:
        limiter.capacity, limiter.rate_per_min = old_capacity, old_rate
        limiter._buckets.clear()


def test_write_rate_limit_separate_bucket(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    # 写桶与严格桶隔离：清空两桶后，严格桶打满不应影响写桶计数
    perfect_main.strict_limiter._buckets.clear()
    perfect_main.write_limiter._buckets.clear()
    old_capacity = perfect_main.write_limiter.capacity
    try:
        perfect_main.write_limiter.capacity = 5
        # 写桶第 5 个请求仍应到达路由（edges 404），证明未受严格桶影响
        for _ in range(5):
            r = api.post("/api/v1/workflow/edges", json={"source": "x", "target": "y"})
            assert r.status_code == 404
        r = api.post("/api/v1/workflow/edges", json={"source": "x", "target": "y"})
        assert r.status_code == 429
    finally:
        perfect_main.write_limiter.capacity = old_capacity
        perfect_main.write_limiter._buckets.clear()


def test_ast_validate_code_size_413(api):
    big = "x" * (512 * 1024 + 1)
    r = api.post("/api/v1/ast/validate", json={"code": big})
    assert r.status_code == 413


def test_node_config_json_size_413(api):
    snap = api.get("/api/v1/workflow").json()
    node_id = snap["nodes"][0]["id"]
    huge_config = {"blob": "y" * (64 * 1024 + 10)}
    r = api.put(f"/api/v1/workflow/nodes/{node_id}/config", json=huge_config)
    assert r.status_code == 413


def test_node_count_limit_413(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("AIGENT_MAX_NODES", "1")  # 低于现有节点数，任何新增都超限
    perfect_main.write_limiter._buckets.clear()
    comp = api.get("/api/v1/components").json()[0]
    r = api.post("/api/v1/workflow/nodes", json={"component_id": comp["id"], "x": 10, "y": 10})
    assert r.status_code == 413


def test_edge_count_limit_413(api, monkeypatch):
    monkeypatch.setenv("AIGENT_MAX_EDGES", "1")  # 低于现有连线数
    perfect_main.write_limiter._buckets.clear()
    snap = api.get("/api/v1/workflow").json()
    nodes = snap["nodes"]
    r = api.post(
        "/api/v1/workflow/edges",
        json={"source": nodes[0]["id"], "target": nodes[1]["id"]},
    )
    assert r.status_code == 413
