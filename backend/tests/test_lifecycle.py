# tests/test_lifecycle.py —— T25：优雅关闭与循环看护
import time

import pytest
from starlette.testclient import TestClient

from perfect_main import app, engine


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def test_readyz_503_after_persistent_dag_failure(api, monkeypatch):
    # 注入持续异常：DAG 循环不吞异常、计数上报；连续 ≥3 次后 readyz 变 503
    calls = {"n": 0}

    async def boom():
        calls["n"] += 1
        raise RuntimeError("injected dag failure for T25")

    monkeypatch.setattr(engine, "_run_dag_round", boom)
    deadline = time.time() + 12
    code, body = 0, {}
    while time.time() < deadline:
        r = api.get("/readyz")
        checks = r.json().get("checks", {})
        if r.status_code == 503 and checks.get("loop_failure_counts", {}).get("dag", 0) >= 3:
            code, body = r.status_code, r.json()
            break
        time.sleep(0.2)
    assert code == 503, f"等待连续失败超时: calls={calls['n']}"
    # 循环本身仍存活（异常被兜住并计数，而非进程崩溃）
    assert body["checks"]["dag_loop_alive"] is True
    assert body["status"] == "not_ready"


def test_readyz_recovers_after_failure_clears(api, monkeypatch):
    # 解除注入后：成功一轮即清零计数，readyz 回到 200（undo 与在途轮有竞态，轮询到双条件满足）
    async def boom():
        raise RuntimeError("injected")

    monkeypatch.setattr(engine, "_run_dag_round", boom)
    time.sleep(3.5)  # 攒几次失败
    monkeypatch.undo()
    deadline = time.time() + 12
    ok = False
    while time.time() < deadline:
        r = api.get("/readyz")
        if r.status_code == 200 and engine.loop_failure_counts["dag"] == 0:
            ok = True
            break
        time.sleep(0.3)
    assert ok, f"counts={engine.loop_failure_counts} readyz={r.status_code if 'r' in dir() else 'n/a'}"


def test_stop_awaits_task_termination():
    import asyncio

    async def scenario():
        engine.start()
        tasks = (engine._engine_task, engine._telemetry_task)
        assert all(t is not None and not t.done() for t in tasks)
        await engine.stop()
        # 优雅关闭：取消后任务真正终止（而非悬空 cancelling）
        await asyncio.sleep(0)
        return all(t.done() for t in tasks if t is not None)

    done_all = asyncio.run(scenario())
    assert done_all is True
    # 收尾恢复循环（本测试用一次性 loop 跑过 start/stop；会话引擎随后由 lifespan 重建）
    asyncio.run(_restart())


async def _restart():
    engine.start()
