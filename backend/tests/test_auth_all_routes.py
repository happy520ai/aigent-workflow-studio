# tests/test_auth_all_routes.py —— T10：全局鉴权中间件
# 覆盖：写路由 401/401/通过、GET 只读策略（AIGENT_PUBLIC_READ）、
#       回环未配置令牌放行、非回环未配置令牌 403、live-app 短期签名 URL、CORS 预检放行。
# 无副作用探针：POST /api/v1/workflow/edges 打不存在的节点 → 鉴权通过后由路由层返回 404，
# 不改动引擎拓扑（对比基线：鉴权失败一律 401/403）。
import time

import pytest
from starlette.testclient import TestClient

import perfect_main
from perfect_main import _sign_live_app, app

PROBE_WRITE = {"source": "no_such_node", "target": "no_such_node2"}


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def test_write_route_token_matrix(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "tok-abc123")
    # 无令牌 → 401
    r = api.post("/api/v1/workflow/edges", json=PROBE_WRITE)
    assert r.status_code == 401
    # 错误令牌 → 401
    r = api.post("/api/v1/workflow/edges", json=PROBE_WRITE, headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 401
    # 正确令牌 → 通过鉴权，路由层因节点不存在返回 404（证明请求已到达路由）
    r = api.post("/api/v1/workflow/edges", json=PROBE_WRITE, headers={"X-Admin-Token": "tok-abc123"})
    assert r.status_code == 404


def test_get_read_policy(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "tok-abc123")
    # 默认（未开 AIGENT_PUBLIC_READ）：GET 只读接口也需要令牌
    assert api.get("/api/v1/workflow").status_code == 401
    r = api.get("/api/v1/workflow", headers={"X-Admin-Token": "tok-abc123"})
    assert r.status_code == 200

    # 开公共读后：GET 免令牌
    monkeypatch.setenv("AIGENT_PUBLIC_READ", "1")
    assert api.get("/api/v1/workflow").status_code == 200
    # 但 /settings/*、/publish/* 永远属于敏感面，公共读不放行
    assert api.get("/api/v1/settings/llm").status_code == 401
    assert api.get("/api/v1/publish/export-zip").status_code == 401


def test_loopback_without_token_allowed(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    # TestClient 即回环等价来源（perfect_main.TRUSTED_LOCAL_HOSTS 含 testclient）：
    # 写路由不要求令牌 → 鉴权放行，路由层 404
    r = api.post("/api/v1/workflow/edges", json=PROBE_WRITE)
    assert r.status_code == 404


def test_non_loopback_without_token_forbidden(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    # 模拟非回环来源：清空本机白名单后任何 client.host 都不可信
    monkeypatch.setattr(perfect_main, "TRUSTED_LOCAL_HOSTS", set())
    r = api.get("/api/v1/workflow")
    assert r.status_code == 403


def test_live_app_signed_url(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "tok-abc123")
    # 无头无签名 → 401
    assert api.get("/api/v1/publish/live-app").status_code == 401

    # 持令牌换取签名 URL
    r = api.get("/api/v1/publish/live-app-url", headers={"X-Admin-Token": "tok-abc123"})
    assert r.status_code == 200
    body = r.json()
    assert body["signed"] is True and "exp=" in body["url"] and "sig=" in body["url"]

    # 免头直开签名 URL → 200 HTML
    r = api.get(body["url"])
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]

    # 过期签名 → 401
    expired_exp = int(time.time()) - 10
    bad = f"/api/v1/publish/live-app?exp={expired_exp}&sig={_sign_live_app(expired_exp, 'tok-abc123')}"
    assert api.get(bad).status_code == 401

    # 篡改签名 → 401
    ok_exp = int(time.time()) + 300
    forged = f"/api/v1/publish/live-app?exp={ok_exp}&sig={'0' * 64}"
    assert api.get(forged).status_code == 401


def test_cors_preflight_bypasses_auth(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "tok-abc123")
    r = api.options(
        "/api/v1/workflow/nodes",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    # CORS 预检必须放行（否则浏览器无法发送带 X-Admin-Token 的正式请求）
    assert r.status_code == 200


def test_health_endpoints_exempt_from_auth(api, monkeypatch):
    # T20：/healthz /readyz 免鉴权——配置令牌后依然可被编排器/负载均衡探测
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "tok-abc123")
    assert api.get("/healthz").status_code == 200
    # readyz 在引擎首跳心跳前会正确返回 503（未就绪）；轮询等待就绪后断言免鉴权 200
    deadline = time.time() + 8
    code = 0
    while time.time() < deadline:
        code = api.get("/readyz").status_code
        if code == 200:
            break
        time.sleep(0.2)
    assert code == 200
