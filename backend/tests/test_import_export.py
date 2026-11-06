# tests/test_import_export.py —— T33：工作流 JSON 导入/导出（往返 + 校验拒绝）
import pytest
from starlette.testclient import TestClient

from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def _snapshot_of(api):
    return api.get("/api/v1/workflow").json()


def test_export_import_roundtrip(api):
    # default 导出 → 导入到 wf_copy → 两者拓扑相等
    exported = api.get("/api/v1/workflows/default/export").json()
    assert exported["schema"] == "aigent-workflow"
    assert exported["schema_version"] == 1
    assert len(exported["nodes"]) == 5

    r = api.post("/api/v1/workflows/wf_copy/import", json=exported)
    assert r.status_code == 200
    try:
        copy_row = api.get("/api/v1/workflows/wf_copy").json()
        assert copy_row["nodes"] == exported["nodes"]
        assert copy_row["edges"] == exported["edges"]
    finally:
        api.delete("/api/v1/workflows/wf_copy")


def test_import_rejects_unknown_node_type(api):
    exported = api.get("/api/v1/workflows/default/export").json()
    exported["nodes"][0]["type"] = "not_a_real_type"
    r = api.post("/api/v1/workflows/wf_bad/import", json=exported)
    assert r.status_code == 400
    assert "未知节点类型" in r.json()["detail"]
    # 失败不落库
    assert api.get("/api/v1/workflows/wf_bad").status_code == 404


def test_import_rejects_cycle(api):
    base = api.get("/api/v1/workflows/default/export").json()
    nodes = base["nodes"][:3]
    ids = [n["id"] for n in nodes]
    edges = [
        {"id": "e1", "source": ids[0], "target": ids[1]},
        {"id": "e2", "source": ids[1], "target": ids[2]},
        {"id": "e3", "source": ids[2], "target": ids[0]},  # 成环
    ]
    r = api.post("/api/v1/workflows/wf_cycle/import", json={"schema": "aigent-workflow", "schema_version": 1, "name": "x", "nodes": nodes, "edges": edges})
    assert r.status_code == 400
    assert "环" in r.json()["detail"]


def test_import_rejects_bad_schema_and_limit(api, monkeypatch):
    base = api.get("/api/v1/workflows/default/export").json()
    # schema 不符
    r = api.post("/api/v1/workflows/wf_x/import", json={**base, "schema": "other"})
    assert r.status_code == 400
    # 版本不符
    r = api.post("/api/v1/workflows/wf_x/import", json={**base, "schema_version": 99})
    assert r.status_code == 400
    # 数量超限
    monkeypatch.setenv("AIGENT_MAX_NODES", "2")
    r = api.post("/api/v1/workflows/wf_x/import", json=base)
    assert r.status_code == 400
    assert "上限" in r.json()["detail"]


def test_import_rejects_dangling_edge(api):
    base = api.get("/api/v1/workflows/default/export").json()
    base["edges"] = [dict(base["edges"][0], source="ghost_node")]
    r = api.post("/api/v1/workflows/wf_ghost/import", json=base)
    assert r.status_code == 400
    assert "不存在" in r.json()["detail"]


def test_import_to_active_workflow_reloads_and_broadcasts(api):
    # 导出到 wf_active_import 并导入 → 激活 → 内存快照与导入内容一致
    exported = api.get("/api/v1/workflows/default/export").json()
    api.post("/api/v1/workflows/wf_active_import/import", json=exported)
    try:
        api.post("/api/v1/workflows/wf_active_import/activate")
        snap = _snapshot_of(api)
        assert snap["workflow_id"] == "wf_active_import"
        assert len(snap["nodes"]) == 5
    finally:
        api.post("/api/v1/workflows/default/activate")
        api.delete("/api/v1/workflows/wf_active_import")


def test_export_unknown_workflow_404(api):
    assert api.get("/api/v1/workflows/never_existed/export").status_code == 404
