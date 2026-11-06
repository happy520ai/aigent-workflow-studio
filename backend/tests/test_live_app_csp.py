# tests/test_live_app_csp.py —— A6(a)：live-app 响应必须带 sandbox CSP（且不带 allow-same-origin）
def test_live_app_has_sandbox_csp(perfect_client):
    resp = perfect_client.get("/api/v1/publish/live-app")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "sandbox" in csp
    # 不透明源隔离：绝不放行 allow-same-origin
    assert "allow-same-origin" not in csp
