# tests/test_security_headers.py —— T14：统一安全响应头
import pytest
from starlette.testclient import TestClient

from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def test_headers_on_plain_get(api):
    r = api.get("/api/v1/workflow")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_headers_on_auth_error_response(api, monkeypatch):
    # 401/429 也要带安全头
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "tok-x")
    r = api.post("/api/v1/workflow/edges", json={"source": "a", "target": "b"})
    assert r.status_code == 401
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_live_app_exempts_x_frame_options(api):
    r = api.get("/api/v1/publish/live-app")
    assert r.status_code == 200
    # live-app 设计为可 iframe：无 XFO，但仍带 nosniff
    assert "X-Frame-Options" not in r.headers
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    # 自身 CSP 仍由路由下发（T15 收紧的是该 CSP 内容）
    assert "Content-Security-Policy" in r.headers
