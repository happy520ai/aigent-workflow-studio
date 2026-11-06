# tests/test_health.py —— T20：/healthz /readyz 健康检查
import pytest
from starlette.testclient import TestClient

from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        # 给双循环至少一跳的时间打上心跳
        import time as _t

        _t.sleep(1.0)
        yield c


def test_healthz_liveness(api):
    r = api.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]  # 版本号存在即可，不暴露内部细节


def test_readyz_reports_ready(api):
    r = api.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    checks = body["checks"]
    assert checks["sqlite_writable"] is True
    assert checks["dag_loop_alive"] is True
    assert checks["telemetry_loop_alive"] is True
    # 心跳年龄 < 5s 且为数值
    assert isinstance(checks["last_tick_age_s"], (int, float))
    assert checks["last_tick_age_s"] < 5.0


def test_readyz_does_not_leak_internals(api):
    body = api.get("/readyz").json()
    text = str(body)
    assert "db_path" not in text
    assert ".db" not in text
    assert "api_key" not in text
