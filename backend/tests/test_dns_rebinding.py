# tests/test_dns_rebinding.py —— T12：LLM api_base 请求时解析复检 + IP 固定直连
# 覆盖：请求时解析到内网 IP → 拒绝（rebinding 场景）、公网解析 → 返回 IP 固定 URL、
#       IPPinnedTransport 保留 Host 头与 SNI、引擎侧 rebinding 检出后按 LLM 失败降级且不外呼。
import asyncio

import httpx
import pytest

import perfect_engine
from perfect_engine import (
    ConnectionManager,
    IPPinnedTransport,
    PerfectNeuralEngine,
    resolve_and_pin_api_base,
)


def make_engine() -> PerfectNeuralEngine:
    return PerfectNeuralEngine(ws_manager=ConnectionManager())


def run(coro):
    return asyncio.run(coro)


def _fake_addrinfo(ip: str):
    return [(2, 1, 6, "", (ip, 0))]


def test_resolver_rejects_private_ip_at_request_time(monkeypatch):
    # 模拟 rebinding：设置期解析是公网，真实请求时第二次解析返回内网 IP → 必须拒绝
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: _fake_addrinfo("192.168.1.10"))
    with pytest.raises(ValueError, match="内网"):
        run(resolve_and_pin_api_base("https://api.example.com/v1"))


def test_resolver_rejects_loopback_and_metadata(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: _fake_addrinfo("127.0.0.1"))
    with pytest.raises(ValueError):
        run(resolve_and_pin_api_base("https://api.example.com/v1"))
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: _fake_addrinfo("169.254.169.254"))
    with pytest.raises(ValueError):
        run(resolve_and_pin_api_base("https://api.example.com/v1"))


def test_resolver_pins_public_ip(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: _fake_addrinfo("93.184.216.34"))
    pinned = run(resolve_and_pin_api_base("https://api.example.com/v1"))
    assert httpx.URL(pinned).host == "93.184.216.34"
    assert str(httpx.URL(pinned).path) == "/v1"


def test_resolver_allows_private_when_explicit(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: _fake_addrinfo("192.168.1.10"))
    pinned = run(resolve_and_pin_api_base("https://api.example.com/v1", allow_private=True))
    assert httpx.URL(pinned).host == "192.168.1.10"


def test_transport_rewrites_host_keeps_host_header_and_sni():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url_host"] = request.url.host
        captured["host_header"] = request.headers.get("Host")
        captured["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, json={"ok": True})

    transport = IPPinnedTransport(pinned_ip="93.184.216.34", inner=httpx.MockTransport(handler))
    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions", json={"a": 1})
    resp = asyncio.run(transport.handle_async_request(req))
    assert resp.status_code == 200
    assert captured["url_host"] == "93.184.216.34"  # 实际按 IP 直连
    assert captured["host_header"] == "api.example.com"  # Host 头保留原域名（虚拟主机路由）
    assert captured["sni"] == "api.example.com"  # TLS SNI 保留原域名（证书校验不受影响）


def test_engine_degrades_when_rebinding_detected(monkeypatch):
    eng = make_engine()
    eng.llm_config = {
        "api_key": "sk-test-not-real",
        "api_base": "https://rebind.example.com/v1",
        "model": "test-model",
    }
    node = eng.nodes["node_ui_gen"]
    before_html = eng.latest_sandbox_html

    async def rebinding_resolver(api_base: str, allow_private: bool = False) -> str:
        raise ValueError("api_base 指向内网/保留地址，已拒绝: 10.0.0.5")

    monkeypatch.setattr(perfect_engine, "resolve_and_pin_api_base", rebinding_resolver)

    async def scenario():
        await eng._execute_single_node(node)

    run(scenario())
    # 降级到内置模板：状态成功、沙盒重新编译，绝不发起真实外呼
    assert node.status == "success"
    assert eng.latest_sandbox_html != before_html
    assert "DOM RENDERER LIVE SANDBOX" in eng.latest_sandbox_html
    assert any("降级内置模板" in line for line in eng.terminal_logs)
