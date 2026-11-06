# tests/test_llm_client.py —— T24：LLM 调用韧性（重试/信号量/超时/降级）
import asyncio

import httpx
import pytest

import llm_client as llm_mod
from llm_client import LLMClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    monkeypatch.setattr(LLMClient, "_backoff", staticmethod(lambda attempt: 0))


def _ok(content="<div>ok</div>"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _factory(handler):
    async def factory():
        return httpx.MockTransport(handler)

    return factory


def test_retry_on_429_then_success():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return _ok()

    client = LLMClient(max_concurrency=1, timeout_s=5)
    result = run(
        client.chat_completion(
            api_base="https://api.example.com/v1",
            api_key="sk-test",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            transport_factory=_factory(handler),
        )
    )
    assert result["ok"] is True and result["degraded"] is False
    assert result["attempts"] == 2
    assert calls["n"] == 2


def test_persistent_5xx_degrades_after_retries():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500)

    client = LLMClient(max_concurrency=1, timeout_s=5)
    result = run(
        client.chat_completion(
            api_base="https://api.example.com/v1",
            api_key="sk-test",
            model="m",
            messages=[],
            transport_factory=_factory(handler),
        )
    )
    # 默认最多 2 次重试 => 共 3 次尝试；最终降级且 degraded=true
    assert calls["n"] == 3
    assert result["ok"] is False and result["degraded"] is True
    assert result["attempts"] == 3


def test_non_retryable_400_fails_fast():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = LLMClient(max_concurrency=1, timeout_s=5)
    result = run(
        client.chat_completion(
            api_base="https://api.example.com/v1",
            api_key="sk-test",
            model="m",
            messages=[],
            transport_factory=_factory(handler),
        )
    )
    assert calls["n"] == 1
    assert result["ok"] is False and result["degraded"] is True


def test_timeout_retried_then_success():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("slow upstream")
        return _ok()

    client = LLMClient(max_concurrency=1, timeout_s=5)
    result = run(
        client.chat_completion(
            api_base="https://api.example.com/v1",
            api_key="sk-test",
            model="m",
            messages=[],
            transport_factory=_factory(handler),
        )
    )
    assert result["ok"] is True and result["attempts"] == 2


def test_semaphore_limits_concurrency():
    state = {"inside": 0, "max": 0}

    def handler(request):
        state["inside"] += 1
        state["max"] = max(state["max"], state["inside"])
        import time as t

        t.sleep(0.15)
        state["inside"] -= 1
        return _ok()

    async def scenario():
        client = LLMClient(max_concurrency=2, timeout_s=5)
        results = await asyncio.gather(
            *(
                client.chat_completion(
                    api_base="https://api.example.com/v1",
                    api_key="sk-test",
                    model="m",
                    messages=[],
                    transport_factory=_factory(handler),
                )
                for _ in range(6)
            )
        )
        return results

    results = run(scenario())
    assert all(r["ok"] for r in results)
    assert state["max"] <= 2  # 信号量生效


def test_transport_factory_error_is_deterministic_failure():
    calls = {"n": 0}

    async def bad_factory():
        calls["n"] += 1
        raise ValueError("api_base 指向内网/保留地址，已拒绝: 10.0.0.5")

    client = LLMClient(max_concurrency=1, timeout_s=5)
    result = run(
        client.chat_completion(
            api_base="https://rebind.example.com/v1",
            api_key="sk-test",
            model="m",
            messages=[],
            transport_factory=bad_factory,
        )
    )
    # T12 解析拒绝不重试
    assert calls["n"] == 1
    assert result["ok"] is False and result["degraded"] is True


def test_engine_sets_degraded_flag_on_node(monkeypatch):
    from perfect_engine import ConnectionManager, PerfectNeuralEngine

    eng = PerfectNeuralEngine(ws_manager=ConnectionManager())
    eng.llm_config = {"api_key": "sk-unit", "api_base": "https://rebind.example.com/v1", "model": "test-model"}
    node = eng.nodes["node_ui_gen"]

    async def rebinding(api_base: str, allow_private: bool = False) -> str:
        raise ValueError("api_base 指向内网/保留地址，已拒绝: 10.0.0.5")

    import perfect_engine as pe

    monkeypatch.setattr(pe, "resolve_and_pin_api_base", rebinding)

    async def scenario():
        await eng._execute_single_node(node)

    run(scenario())
    # T24：降级必须在节点状态里可见（前端徽章数据源）
    assert node.degraded is True
    assert node.status == "success"
    assert any("降级内置模板" in line for line in eng.terminal_logs)


def test_engine_clears_degraded_on_builtin_mode():
    from perfect_engine import ConnectionManager, PerfectNeuralEngine

    eng = PerfectNeuralEngine(ws_manager=ConnectionManager())
    eng.llm_config = {"api_key": "", "api_base": "https://api.example.com/v1", "model": "m"}
    node = eng.nodes["node_ui_gen"]

    async def scenario():
        await eng._execute_single_node(node)

    run(scenario())
    assert node.degraded is False
    snap = eng.get_snapshot()
    assert all(n.degraded is False for n in snap.nodes)
