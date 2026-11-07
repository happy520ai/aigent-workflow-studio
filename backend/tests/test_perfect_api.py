# tests/test_perfect_api.py —— perfect_main REST + WebSocket 集成测试（真实后台 DAG 循环）
import json
import os
import time

import pytest
from starlette.testclient import TestClient

from perfect_main import app


@pytest.fixture(scope="module")
def perfect_client():
    with TestClient(app) as c:
        # 等待遥测历史队列填满（CPU/内存 16 点、ECG 20 点），消除时序抖动
        deadline = time.time() + 8
        while time.time() < deadline:
            snap = c.get("/api/v1/workflow").json()
            if (
                len(snap["telemetry"]["cpu_history"]) >= 16
                and len(snap["telemetry"]["ecg_waveform"]) >= 20
            ):
                break
            time.sleep(0.2)
        yield c


def teardown_module(module):
    # 清理引擎在 cwd 产生的 SQLite 断点库（幂等）
    db = os.path.join(os.getcwd(), "aigent_checkpoints.db")
    if os.path.exists(db):
        try:
            os.remove(db)
        except OSError:
            pass
    # 重建同 schema 的 checkpoints 表（与 bootstrap_studio.py 一致），
    # 兼容根目录 test_workflow_e2e.py::test_04 对该库的依赖
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                state_payload TEXT NOT NULL,
                generated_code TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _recv_until(ws, event_name, timeout_s=6.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        msg = json.loads(ws.receive_text())
        if msg.get("event") == event_name:
            return msg
    raise AssertionError(f"超时未收到事件 {event_name}")


def test_perfect_docs_and_routes(perfect_client):
    assert perfect_client.get("/docs").status_code == 200
    spec = perfect_client.get("/openapi.json").json()
    assert "/api/v1/workflow/nodes" in spec["paths"]
    assert "/api/v1/workflow/nodes/{node_id}/position" in spec["paths"]
    assert "/api/v1/checkpoints" in spec["paths"]
    assert "/api/v1/sandbox/preview" in spec["paths"]


def test_perfect_snapshot_contract(perfect_client):
    snap = perfect_client.get("/api/v1/workflow").json()
    assert snap["version"] == "v3.0.0"
    assert len(snap["nodes"]) == 5
    assert len(snap["edges"]) == 4
    # 节点坐标与文档一致（55/235、305/235、610/95、610/305、610/435）
    pos = {n["id"]: (n["position"]["x"], n["position"]["y"]) for n in snap["nodes"]}
    assert pos["node_event_capturer"] == (55.0, 235.0)
    assert pos["node_intent_agent"] == (305.0, 235.0)
    assert pos["node_ui_gen"] == (610.0, 95.0)
    assert pos["node_co_agent"] == (610.0, 305.0)
    assert pos["node_dom_renderer"] == (610.0, 435.0)


def test_perfect_components_search(perfect_client):
    items = perfect_client.get("/api/v1/components").json()
    # T30 新增 2 个真实算子组件（llm_generic/http_request）：12 -> 14
    assert len(items) == 14
    items = perfect_client.get("/api/v1/components", params={"q": "NLU"}).json()
    assert [i["id"] for i in items] == ["perc_nlu"]
    items = perfect_client.get("/api/v1/components", params={"q": "发布"}).json()
    assert [i["id"] for i in items] == ["dep_publish"]


def test_position_and_config_endpoints(perfect_client):
    resp = perfect_client.patch(
        "/api/v1/workflow/nodes/node_ui_gen/position", json={"x": 650.0, "y": 120.0}
    )
    assert resp.status_code == 200
    assert resp.json()["position"] == {"x": 650.0, "y": 120.0}
    resp = perfect_client.patch("/api/v1/workflow/nodes/ghost/position", json={"x": 1, "y": 1})
    assert resp.status_code == 404

    resp = perfect_client.put("/api/v1/workflow/nodes/node_ui_gen/config", json={"role": "pytest-perfect"})
    assert resp.status_code == 200
    assert resp.json()["config_json"] == {"role": "pytest-perfect"}
    resp = perfect_client.put("/api/v1/workflow/nodes/ghost/config", json={})
    assert resp.status_code == 404


def test_checkpoints_endpoint(perfect_client):
    resp = perfect_client.get("/api/v1/checkpoints", params={"limit": 5})
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert 1 <= len(rows) <= 5  # 引擎循环运行中，断点持续入库
    row = rows[0]
    assert set(row) == {
        "checkpoint_id", "run_id", "node_id", "timestamp", "state_payload", "generated_code",
    }
    assert row["checkpoint_id"].startswith("ckpt_")
    assert row["node_id"] in {n["id"] for n in perfect_client.get("/api/v1/workflow").json()["nodes"]}
    assert isinstance(row["state_payload"], dict)


def test_sandbox_preview_endpoint(perfect_client):
    resp = perfect_client.get("/api/v1/sandbox/preview")
    assert resp.status_code == 200
    data = resp.json()
    assert "DOM RENDERER LIVE SANDBOX" in data["html"]
    assert data["memory_bus"]["dom_hydration_status"] == "READY"


def test_create_node_from_sidebar_endpoint(perfect_client):
    resp = perfect_client.post(
        "/api/v1/workflow/nodes",
        json={"component_id": "dep_publish", "x": 700.0, "y": 300.0},
    )
    assert resp.status_code == 200
    node = resp.json()
    assert node["id"].startswith("node_dep_publish_")
    assert node["theme_color"] == "#ec4899"

    snap = perfect_client.get("/api/v1/workflow").json()
    assert len(snap["nodes"]) == 6
    assert any(
        e["target"] == node["id"] and e["source"] == "node_intent_agent"
        for e in snap["edges"]
    )

    resp = perfect_client.post("/api/v1/workflow/nodes", json={"component_id": "nope"})
    assert resp.status_code == 400


def test_perfect_control_cycle_and_reset_restores_topology(perfect_client):
    r = perfect_client.post("/api/v1/workflow/control", json={"action": "pause"})
    assert r.json()["project_status"] == "已暂停"
    r = perfect_client.post("/api/v1/workflow/control", json={"action": "run"})
    assert r.json()["project_status"] == "运行中"
    r = perfect_client.post("/api/v1/workflow/control", json={"action": "debug"})
    assert r.json()["project_status"] == "调试中"
    r = perfect_client.post("/api/v1/workflow/control", json={"action": "reset"})
    assert r.json()["project_status"] == "运行中"
    snap = r.json()
    # RESET 复原拓扑（含前面注入的第 6 个节点与被改写的坐标/配置）
    assert len(snap["nodes"]) == 5
    assert len(snap["edges"]) == 4
    assert perfect_client.post("/api/v1/workflow/control", json={"action": "shutdown"}).status_code == 422


def test_perfect_ws_snapshot_telemetry_and_selection(perfect_client):
    with perfect_client.websocket_connect("/ws/telemetry") as ws:
        # 1) 首连下发完整快照 + 顶层 sandbox_html
        first = _recv_until(ws, "workflow_snapshot")
        assert first["data"]["version"] == "v3.0.0"
        assert isinstance(first["sandbox_html"], str)
        assert "DOM RENDERER" in first["sandbox_html"]

        # 2) 遥测节拍：A8 瘦身后不再携带 sandbox_html 与 shared_memory_bus
        tick = _recv_until(ws, "telemetry_tick")
        assert "sandbox_html" not in tick["data"]
        assert "shared_memory_bus" not in tick["data"]
        assert len(tick["data"]["edges"]) >= 4
        assert 10 <= len(tick["data"]["cpu_history"]) <= 16

        # 3) node_update 事件携带完整节点、沙盒代码与共享记忆总线
        upd = _recv_until(ws, "node_update")
        assert "node" in upd["data"]
        assert isinstance(upd["data"]["sandbox_html"], str)
        assert "shared_memory_bus" in upd["data"]

        # 4) select_node 指令回执
        ws.send_json({"type": "select_node", "node_id": "node_co_agent"})
        sel = _recv_until(ws, "selected_node_changed")
        assert sel["data"]["id"] == "node_co_agent"
