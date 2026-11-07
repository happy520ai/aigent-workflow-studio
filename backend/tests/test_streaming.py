# tests/test_streaming.py —— T31：SSE 流式输出与 node_stream 事件
import asyncio

import httpx

from llm_client import LLMClient
from perfect_engine import ConnectionManager, PerfectNeuralEngine


def run(coro):
    return asyncio.run(coro)


def _sse_response(chunks):
    body = "".join(
        f'data: {{"choices": [{{"delta": {{"content": "{c}"}}}}]}}\n\n' for c in chunks
    ) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode("utf-8"))


def _factory(handler):
    async def factory():
        return httpx.MockTransport(handler)

    return factory


def test_stream_yields_deltas_in_order():
    async def factory():
        return httpx.MockTransport(lambda request: _sse_response(["<div>", "hello", "</div>"]))

    client = LLMClient(max_concurrency=1, timeout_s=5)

    async def scenario():
        out = []
        async for chunk in client.chat_completion_stream(
            api_base="https://api.example.com/v1",
            api_key="sk-test",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            transport_factory=factory,
        ):
            out.append(chunk)
        return out

    chunks = run(scenario())
    deltas = [c["delta"] for c in chunks if c["delta"]]
    assert deltas == ["<div>", "hello", "</div>"]
    assert chunks[-1]["done"] is True
    assert chunks[-1]["degraded"] is False


def test_stream_http_error_degrades():
    async def factory():
        return httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))

    client = LLMClient(max_concurrency=1, timeout_s=5)

    async def scenario():
        out = []
        async for chunk in client.chat_completion_stream(
            api_base="https://api.example.com/v1",
            api_key="sk-test",
            model="m",
            messages=[],
            transport_factory=factory,
        ):
            out.append(chunk)
        return out

    chunks = run(scenario())
    assert chunks[-1]["done"] is True
    assert chunks[-1]["degraded"] is True
    assert "500" in chunks[-1]["error"]


class RecordingManager(ConnectionManager):
    """记录 broadcast 调用用于断言（无真实 WS 连接）"""

    def __init__(self) -> None:
        super().__init__()
        self.events: list = []

    async def broadcast(self, event_type: str, payload) -> None:
        self.events.append((event_type, payload))


def test_engine_broadcasts_node_stream_then_final_update(monkeypatch):
    eng = PerfectNeuralEngine(ws_manager=RecordingManager())
    eng.llm_config = {"api_key": "sk-unit", "api_base": "https://api.example.com/v1", "model": "m"}
    node = eng.nodes["node_ui_gen"]

    # 打桩：IPPinnedTransport 直接返回 MockTransport（避免真实网络）；解析跳过 DNS
    async def fake_resolve(api_base: str, allow_private: bool = False, validate_ip_literals: bool = False) -> str:
        return api_base

    monkeypatch.setattr("perfect_engine.resolve_and_pin_api_base", fake_resolve)
    monkeypatch.setattr(
        "perfect_engine.IPPinnedTransport",
        lambda pinned_ip, inner=None: httpx.MockTransport(
            lambda request: _sse_response(["<div id='a'>A</div>", "<span>B</span>"])
        ),
    )

    async def scenario():
        await eng._execute_single_node(node)

    run(scenario())

    stream_events = [p for (ev, p) in eng.ws_manager.events if ev == "node_stream"]
    updates = [p for (ev, p) in eng.ws_manager.events if ev == "node_update"]
    # 增量事件：node_id + delta，按序
    assert [s["delta"] for s in stream_events] == ["<div id='a'>A</div>", "<span>B</span>"]
    assert all(s["node_id"] == node.id for s in stream_events)
    # 最终态仍由 node_update 携带完整沙盒
    assert updates and updates[-1]["node"]["id"] == node.id
    assert node.degraded is False
    assert "<span>B</span>" in eng.latest_sandbox_html
