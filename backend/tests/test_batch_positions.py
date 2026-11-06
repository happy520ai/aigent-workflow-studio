# tests/test_batch_positions.py —— T35：自动布局批量落位端点
import pytest
from starlette.testclient import TestClient

from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def _node_ids(api):
    return [n["id"] for n in api.get("/api/v1/workflow").json()["nodes"]]


def test_batch_positions_updates_layout(api):
    ids = _node_ids(api)
    payload = {"positions": [{"id": nid, "x": 100.0 + i * 50, "y": 200.0 + i * 30} for i, nid in enumerate(ids)]}
    r = api.patch("/api/v1/workflow/positions", json=payload)
    assert r.status_code == 200
    assert r.json()["updated"] == len(ids)
    assert r.json()["skipped"] == 0
    snap = api.get("/api/v1/workflow").json()
    by_id = {n["id"]: n for n in snap["nodes"]}
    for i, nid in enumerate(ids):
        assert by_id[nid]["position"]["x"] == 100.0 + i * 50
        assert by_id[nid]["position"]["y"] == 200.0 + i * 30


def test_batch_positions_skips_unknown_and_404_when_all_invalid(api):
    r = api.patch(
        "/api/v1/workflow/positions",
        json={"positions": [{"id": "ghost", "x": 1, "y": 1}, {"id": "ghost2", "x": 2, "y": 2}]},
    )
    assert r.status_code == 404
