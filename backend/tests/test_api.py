# tests/test_api.py —— REST API 集成测试（会话级 TestClient，真实后台引擎循环）
NODE_IDS = {
    "node_event_capturer", "node_intent_agent", "node_ui_gen",
    "node_co_agent", "node_dom_renderer",
}


def test_docs_and_openapi_available(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert "/api/v1/components" in spec["paths"]
    assert "/api/v1/workflow" in spec["paths"]
    assert "/api/v1/workflow/control" in spec["paths"]
    assert "/api/v1/workflow/nodes/{node_id}/config" in spec["paths"]
    assert "/api/v1/search" in spec["paths"]


def test_component_library_default(client):
    resp = client.get("/api/v1/components")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 12
    assert {it["category_en"] for it in items} == {
        "Triggers", "Perception", "Agents", "Logic", "Frontend", "Deploy",
    }


def test_component_search_chinese_and_english(client):
    resp = client.get("/api/v1/components", params={"q": "触发"})
    assert [it["id"] for it in resp.json()] == ["trig_events", "trig_schedule"]

    resp = client.get("/api/v1/components", params={"q": "agent"})
    ids = {it["id"] for it in resp.json()}
    assert "agent_intent" in ids

    resp = client.get("/api/v1/components", params={"q": "render"})
    assert [it["id"] for it in resp.json()] == ["fe_render"]

    resp = client.get("/api/v1/components", params={"q": "不存在的算子xyz"})
    assert resp.json() == []


def test_workflow_snapshot_contract(client):
    resp = client.get("/api/v1/workflow")
    assert resp.status_code == 200
    snap = resp.json()
    assert snap["version"] == "v2.8"
    assert snap["project_status"] in {"已就绪", "运行中", "已暂停", "调试中", "异常"}
    assert {n["id"] for n in snap["nodes"]} == NODE_IDS
    assert len(snap["edges"]) == 4
    telemetry = snap["telemetry"]
    assert len(telemetry["cpu_history"]) == 16
    assert len(telemetry["memory_history"]) == 16
    assert len(telemetry["ecg_waveform"]) == 20
    assert set(telemetry["radar_metrics"]) == {
        "radar_perception", "responsiveness", "accuracy", "concurrency", "stability",
    }
    assert 0 < len(snap["terminal_logs"]) <= 12


def test_node_config_update_roundtrip(client):
    payload = {"name": "Agentinightik.eod", "role": "pytest-patched"}
    resp = client.put("/api/v1/workflow/nodes/node_ui_gen/config", json=payload)
    assert resp.status_code == 200
    assert resp.json()["config_json"] == payload
    # 快照中同步生效
    snap = client.get("/api/v1/workflow").json()
    target = next(n for n in snap["nodes"] if n["id"] == "node_ui_gen")
    assert target["config_json"]["role"] == "pytest-patched"
    # 未知节点 → 404
    resp = client.put("/api/v1/workflow/nodes/node_ghost/config", json={})
    assert resp.status_code == 404


def test_global_search_hits_nodes_components_logs(client):
    resp = client.get("/api/v1/search", params={"q": "意图"})
    data = resp.json()
    assert data["query"] == "意图"
    assert any(n["id"] == "node_intent_agent" for n in data["nodes"])
    assert any(c["id"] == "agent_intent" for c in data["components"])

    resp = client.get("/api/v1/search", params={"q": "Success"})
    assert any("Success" in line for line in resp.json()["logs"])

    resp = client.get("/api/v1/search")
    assert resp.status_code == 422  # 缺少必填 q


def test_control_full_cycle_restores_running(client):
    resp = client.post("/api/v1/workflow/control", json={"action": "pause"})
    assert resp.status_code == 200
    assert resp.json()["project_status"] == "已暂停"

    resp = client.post("/api/v1/workflow/control", json={"action": "run"})
    assert resp.json()["project_status"] == "运行中"

    resp = client.post("/api/v1/workflow/control", json={"action": "debug"})
    assert resp.json()["project_status"] == "调试中"

    resp = client.post("/api/v1/workflow/control", json={"action": "reset"})
    assert resp.json()["project_status"] == "运行中"

    resp = client.post("/api/v1/workflow/control", json={"action": "shutdown"})
    assert resp.status_code == 422  # 非法动作被 Pydantic 枚举拦截


def test_snapshot_reflects_control_state(client):
    resp = client.post("/api/v1/workflow/control", json={"action": "pause"})
    assert resp.json()["project_status"] == "已暂停"
    snap = client.get("/api/v1/workflow").json()
    assert snap["project_status"] == "已暂停"
    client.post("/api/v1/workflow/control", json={"action": "run"})
