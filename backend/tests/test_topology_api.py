# tests/test_topology_api.py —— A5：连线校验链（404/400/409）+ 删除节点级联 + connect_from
import pytest
from starlette.testclient import TestClient

from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def test_edge_validation_chain(api):
    # 1) 源不存在 → 404
    r = api.post("/api/v1/workflow/edges", json={"source": "ghost", "target": "node_ui_gen"})
    assert r.status_code == 404

    # 2) 自环 → 400
    r = api.post("/api/v1/workflow/edges", json={"source": "node_ui_gen", "target": "node_ui_gen"})
    assert r.status_code == 400
    assert "自环" in r.json()["detail"]

    # 3) 已存在同向边（intent -> ui_gen 是默认边 edge_2_3a）→ 409
    r = api.post(
        "/api/v1/workflow/edges",
        json={"source": "node_intent_agent", "target": "node_ui_gen"},
    )
    assert r.status_code == 409
    assert "已存在" in r.json()["detail"]

    # 4) 成环（ui_gen -> event_capturer，event 沿默认边可达 ui_gen）→ 409
    r = api.post(
        "/api/v1/workflow/edges",
        json={"source": "node_ui_gen", "target": "node_event_capturer"},
    )
    assert r.status_code == 409
    assert "环路" in r.json()["detail"]

    # 全程未新增任何边
    snap = api.get("/api/v1/workflow").json()
    assert len(snap["edges"]) == 4


def test_delete_node_cascades_edges_and_404(api):
    r = api.post("/api/v1/workflow/nodes", json={"component_id": "dep_publish", "x": 700, "y": 300})
    assert r.status_code == 200
    node_id = r.json()["id"]

    snap = api.get("/api/v1/workflow").json()
    assert any(e["target"] == node_id for e in snap["edges"])

    r = api.delete(f"/api/v1/workflow/nodes/{node_id}")
    assert r.status_code == 200
    assert r.json() == {"deleted": node_id}

    snap = api.get("/api/v1/workflow").json()
    assert all(n["id"] != node_id for n in snap["nodes"])
    # 关联连线级联移除
    assert all(e["target"] != node_id and e["source"] != node_id for e in snap["edges"])

    # 再删 → 404
    r = api.delete(f"/api/v1/workflow/nodes/{node_id}")
    assert r.status_code == 404


def test_connect_from_explicit_and_default(api):
    # 显式 connect_from：新节点连到指定父节点
    r = api.post(
        "/api/v1/workflow/nodes",
        json={"component_id": "dep_test", "x": 460, "y": 520, "connect_from": "node_dom_renderer"},
    )
    assert r.status_code == 200
    explicit_id = r.json()["id"]
    snap = api.get("/api/v1/workflow").json()
    assert any(
        e["source"] == "node_dom_renderer" and e["target"] == explicit_id for e in snap["edges"]
    )

    # 默认行为（不传 connect_from）：连接 node_intent_agent
    r = api.post("/api/v1/workflow/nodes", json={"component_id": "dep_test", "x": 460, "y": 520})
    default_id = r.json()["id"]
    snap = api.get("/api/v1/workflow").json()
    assert any(
        e["source"] == "node_intent_agent" and e["target"] == default_id for e in snap["edges"]
    )

    # 清理（加几个删几个，不给其他测试留下脏拓扑）
    for nid in (explicit_id, default_id):
        assert api.delete(f"/api/v1/workflow/nodes/{nid}").status_code == 200
