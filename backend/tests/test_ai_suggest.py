# tests/test_ai_suggest.py —— T34：AI 生成节点（严格 JSON 增量；恶意输出全部被拒）
import json

import httpx
import pytest
from starlette.testclient import TestClient

import perfect_main
from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def _stub_llm(monkeypatch, content: str, ok: bool = True, error: str = None):
    # 大多数用例需要 LLM 可用：默认注入测试 key（503 用例会自行覆盖为空）
    monkeypatch.setitem(perfect_main.engine.llm_config, "api_key", "sk-unit")

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def chat_completion(self, **kwargs):
            if ok:
                return {"ok": True, "content": content, "degraded": False, "error": None, "attempts": 1}
            return {"ok": False, "content": "", "degraded": True, "error": error or "unit failure", "attempts": 3}

    monkeypatch.setattr(perfect_main, "LLMClient", FakeClient)

    async def fake_resolve(api_base: str, allow_private: bool = False, validate_ip_literals: bool = False) -> str:
        return api_base

    monkeypatch.setattr(perfect_main, "resolve_and_pin_api_base", fake_resolve)
    monkeypatch.setattr(
        perfect_main, "IPPinnedTransport", lambda pinned_ip, inner=None: httpx.MockTransport(lambda r: httpx.Response(200))
    )


def _good_suggestion():
    return {
        "nodes": [
            {"id": "ai_n1", "type": "perc_nlu", "title": "AI 意图解析", "subtitle": "(AI)", "x": 120, "y": 60},
            {"id": "ai_n2", "type": "http_request", "title": "AI 出站", "subtitle": "(AI)", "x": 320, "y": 60},
        ],
        "edges": [{"id": "ai_e1", "source": "ai_n1", "target": "ai_n2"}],
    }


def _topology_fingerprint(api):
    snap = api.get("/api/v1/workflow").json()
    return (len(snap["nodes"]), tuple(sorted(n["id"] for n in snap["nodes"])), len(snap["edges"]))


def test_ai_suggest_applies_valid_increment(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "")  # 本机直连
    _stub_llm(monkeypatch, json.dumps(_good_suggestion()))
    before = _topology_fingerprint(api)
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "做一个先解析意图再发 HTTP 的流程"})
    assert r.status_code == 200
    body = r.json()
    assert body["added_nodes"] == 2 and body["added_edges"] == 1
    after = _topology_fingerprint(api)
    assert set(after[1]) - set(before[1]) == {"ai_n1", "ai_n2"}
    assert after[2] == before[2] + 1
    # 清理新增节点
    for nid in ("ai_n1", "ai_n2"):
        api.delete(f"/api/v1/workflow/nodes/{nid}")


def test_ai_suggest_rejects_unknown_type_and_keeps_topology(api, monkeypatch):
    _stub_llm(monkeypatch, json.dumps({"nodes": [{"id": "ai_bad", "type": "evil_type", "title": "x", "subtitle": "s"}], "edges": []}))
    before = _topology_fingerprint(api)
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "恶意输出"})
    assert r.status_code == 400
    assert _topology_fingerprint(api) == before


def test_ai_suggest_rejects_cycle(api, monkeypatch):
    s = _good_suggestion()
    s["edges"].append({"id": "ai_e2", "source": "ai_n2", "target": "ai_n1"})  # 自成环
    _stub_llm(monkeypatch, json.dumps(s))
    before = _topology_fingerprint(api)
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "成环建议"})
    assert r.status_code == 400
    assert "环" in r.json()["detail"]
    assert _topology_fingerprint(api) == before


def test_ai_suggest_rejects_existing_id_collision(api, monkeypatch):
    s = _good_suggestion()
    s["nodes"][0]["id"] = "node_ui_gen"  # 冒充现有节点
    _stub_llm(monkeypatch, json.dumps(s))
    before = _topology_fingerprint(api)
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "撞 id"})
    assert r.status_code == 400
    assert _topology_fingerprint(api) == before


def test_ai_suggest_requires_ai_prefix(api, monkeypatch):
    s = _good_suggestion()
    s["nodes"][0]["id"] = "rogue_1"
    _stub_llm(monkeypatch, json.dumps(s))
    before = _topology_fingerprint(api)
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "无前缀"})
    assert r.status_code == 400
    assert _topology_fingerprint(api) == before


def test_ai_suggest_rejects_malformed_json(api, monkeypatch):
    _stub_llm(monkeypatch, "好的，这是我的建议：节点1连节点2，祝你好运！")
    before = _topology_fingerprint(api)
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "闲话输出"})
    assert r.status_code == 400
    assert _topology_fingerprint(api) == before


def test_ai_suggest_503_without_api_key(api, monkeypatch):
    class FakeCfgEngine:
        pass

    monkeypatch.setitem(perfect_main.engine.llm_config, "api_key", "")
    before = _topology_fingerprint(api)
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "任意"})
    assert r.status_code == 503
    assert _topology_fingerprint(api) == before


def test_ai_suggest_502_on_llm_failure(api, monkeypatch):
    monkeypatch.setitem(perfect_main.engine.llm_config, "api_key", "sk-unit")
    _stub_llm(monkeypatch, "", ok=False, error="upstream down")
    before = _topology_fingerprint(api)
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "任意"})
    assert r.status_code == 502
    assert _topology_fingerprint(api) == before


def test_ai_suggest_empty_prompt_400(api):
    r = api.post("/api/v1/workflow/ai-suggest", json={"prompt": "   "})
    assert r.status_code == 400
