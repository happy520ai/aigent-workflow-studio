# tests/test_real_operators.py —— T30：真实算子框架（llm_generic / http_request / logic_transform）
import asyncio

import httpx

from operator_registry import NeuralOperatorRegistry


def run(coro):
    return asyncio.run(coro)


def _mock_factory(handler):
    async def factory():
        return httpx.MockTransport(handler)

    return factory


# ======================= llm_generic =======================

def _llm_registry(monkeypatch, api_key="sk-test", handler=None):
    reg = NeuralOperatorRegistry(
        llm_config_provider=lambda: {
            "api_key": api_key,
            "api_base": "https://api.example.com/v1",
            "model": "unit-model",
        },
        llm_transport_factory=_mock_factory(handler) if handler else None,
    )
    return reg


def test_llm_generic_success_with_template(monkeypatch):
    calls = {}

    def handler(request):
        calls["body"] = request.read()  # bytes，测试内 json.loads 解析
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hello transformed"}}]})

    reg = _llm_registry(monkeypatch, handler=handler)
    result = run(
        reg.execute(
            "llm_generic",
            {"system_template": "Be terse.", "user_template": "Summarize {{payload.title}} for {{user}}"},
            {},
            inputs={"node_a": {"payload": {"title": "DAG"}, "user": "甲方"}},
        )
    )
    assert result["mode"] == "real"
    assert result["status"] == "completed"
    assert result["output"]["text"] == "Hello transformed"
    # 模板变量取自上游 _inputs（body 为 JSON，中文可能被转义）
    import json as _json

    body = _json.loads(calls["body"].decode("utf-8"))
    assert body["messages"][1]["content"] == "Summarize DAG for 甲方"


def test_llm_generic_no_api_key_never_fakes(monkeypatch):
    reg = _llm_registry(monkeypatch, api_key="")
    result = run(reg.execute("llm_generic", {"user_template": "hi"}, {}, inputs={}))
    assert result["mode"] == "real"
    assert result["status"] == "skipped_no_api_key"
    assert "output" in result


def test_llm_generic_failure_reports_degraded(monkeypatch):
    def handler(request):
        return httpx.Response(500)

    reg = _llm_registry(monkeypatch, handler=handler)
    result = run(reg.execute("llm_generic", {"user_template": "hi"}, {}, inputs={}))
    assert result["mode"] == "real"
    assert result["status"] == "llm_failed"
    assert result["degraded"] is True


def test_llm_generic_uses_runtime_provider_model(monkeypatch):
    import json as _json

    seen = {}

    def handler(request):
        seen["body"] = _json.loads(request.read().decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    reg = _llm_registry(monkeypatch, handler=handler)
    run(reg.execute("llm_generic", {"user_template": "hi", "model": "override-model"}, {}, inputs={}))
    assert seen["body"]["model"] == "override-model"


# ======================= http_request =======================

def test_http_request_get_success():
    reg = NeuralOperatorRegistry(
        http_transport_factory=_mock_factory(
            lambda request: httpx.Response(200, text="pong", headers={"x-echo": request.headers.get("x-tag", "")})
        )
    )
    result = run(
        reg.execute(
            "http_request",
            {"method": "GET", "url": "https://api.example.com/ping", "headers": {"x-tag": "unit"}},
            {},
        )
    )
    assert result["mode"] == "real"
    assert result["status"] == "completed"
    assert result["output"]["status_code"] == 200
    assert result["output"]["body"] == "pong"


def test_http_request_post_body_and_truncation():
    reg = NeuralOperatorRegistry(
        http_transport_factory=_mock_factory(
            lambda request: httpx.Response(200, text="y" * 100)
        )
    )
    result = run(
        reg.execute(
            "http_request",
            {"method": "POST", "url": "https://api.example.com/echo", "body": {"k": "v"}, "max_response_bytes": 10},
            {},
        )
    )
    assert result["output"]["truncated"] is True
    assert len(result["output"]["body"]) == 10


def test_http_request_private_ip_rejected(monkeypatch):
    # 用户自填 URL 的 IP 字面量直检：127.0.0.1 必须被拒（http_request 场景无 LLM 本地部署豁免）
    reg = NeuralOperatorRegistry()
    result = run(
        reg.execute("http_request", {"method": "GET", "url": "http://127.0.0.1:9/secret"}, {})
    )
    assert result["mode"] == "real"
    assert result["status"] == "blocked_by_ssrf_guard"
    assert "内网" in result["output"]["error"]


def test_http_request_private_dns_rejected(monkeypatch):
    # DNS rebinding 场景：请求时解析到内网 IP → 拒绝且不外呼
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(2, 1, 6, "", ("10.1.2.3", 0))])
    reg = NeuralOperatorRegistry()
    result = run(reg.execute("http_request", {"method": "GET", "url": "https://rebind.example.com/"}, {}))
    assert result["status"] == "blocked_by_ssrf_guard"


def test_http_request_invalid_method():
    reg = NeuralOperatorRegistry(
        http_transport_factory=_mock_factory(lambda request: httpx.Response(200))
    )
    result = run(reg.execute("http_request", {"method": "TRACE", "url": "https://api.example.com/"}, {}))
    assert result["status"] == "invalid_method"


def test_http_request_http_error_status_kept():
    reg = NeuralOperatorRegistry(
        http_transport_factory=_mock_factory(lambda request: httpx.Response(404, text="nope"))
    )
    result = run(reg.execute("http_request", {"method": "GET", "url": "https://api.example.com/x"}, {}))
    assert result["status"] == "http_error"
    assert result["output"]["status_code"] == 404


# ======================= logic_transform =======================

def test_logic_transform_dot_path_and_constant():
    reg = NeuralOperatorRegistry()
    result = run(
        reg.execute(
            "logic_transform",
            {
                "mappings": [
                    {"target": "title", "source": "node_a.payload.title"},
                    {"target": "first_item", "source": "node_a.items.0"},
                    {"target": "constant", "value": 42},
                    {"target": "missing", "source": "no.such.path", "default": "fallback"},
                ]
            },
            {},
            inputs={"node_a": {"payload": {"title": "T"}, "items": ["a", "b"]}},
        )
    )
    assert result["mode"] == "real"
    out = result["output"]
    assert out == {"title": "T", "first_item": "a", "constant": 42, "missing": "fallback"}


def test_logic_transform_template_interpolation():
    reg = NeuralOperatorRegistry()
    result = run(
        reg.execute(
            "logic_transform",
            {"mappings": [{"target": "greeting", "template": "你好 {{user}}，共 {{count}} 条"}]},
            {},
            inputs={"u1": {"user": "乙", "count": 3}},
        )
    )
    assert result["output"]["greeting"] == "你好 乙，共 3 条"


def test_logic_transform_no_mappings_keeps_legacy_behavior():
    reg = NeuralOperatorRegistry()
    result = run(reg.execute("logic_transform", {}, {"bus_key": 1}, inputs={"n1": {"x": 1}}))
    out = result["output"]
    assert out["normalized_keys"] == ["n1"]
    assert result["mode"] == "real"


def test_logic_transform_is_eval_free():
    # 恶意配置（含 __import__/eval 形态的字符串）只能作为字面数据出现，绝不执行
    reg = NeuralOperatorRegistry()
    result = run(
        reg.execute(
            "logic_transform",
            {"mappings": [{"target": "evil", "value": "__import__('os').system('echo pwned')"}]},
            {},
        )
    )
    assert result["output"]["evil"] == "__import__('os').system('echo pwned')"


# ======================= 分类标注 =======================

def test_mode_tagging_real_vs_simulated():
    reg = NeuralOperatorRegistry()
    assert run(reg.execute("trig_events", {}, {}))["mode"] == "simulated"
    assert run(reg.execute("unknown_xyz", {"a": 1}, {}))["mode"] == "simulated"
    assert run(reg.execute("logic_transform", {}, {}))["mode"] == "real"
