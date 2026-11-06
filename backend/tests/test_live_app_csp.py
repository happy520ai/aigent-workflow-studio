# tests/test_live_app_csp.py —— A6(a)：live-app 响应必须带 sandbox CSP（且不带 allow-same-origin）
def test_live_app_has_sandbox_csp(perfect_client):
    resp = perfect_client.get("/api/v1/publish/live-app")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "sandbox" in csp
    # 不透明源隔离：绝不放行 allow-same-origin
    assert "allow-same-origin" not in csp


# —— T15：CSP 收紧（追加用例，不改既有断言）——


def test_live_app_csp_no_external_cdn_and_no_inline_script(perfect_client):
    resp = perfect_client.get("/api/v1/publish/live-app")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy", "")
    # 外部 Tailwind CDN 必须退出白名单
    assert "cdn.tailwindcss.com" not in csp
    # 脚本不再放行内联（净化产物保证无 <script>，唯一脚本为本地 vendor）
    assert "'unsafe-inline' script-src" not in csp
    script_directive = next(
        (part for part in csp.split(";") if part.strip().startswith("script-src")), ""
    )
    assert "'unsafe-inline'" not in script_directive
    # 唯一允许的脚本是本地 vendor 的 Tailwind Play
    assert "/static/vendor/tailwindcss-play.js" in script_directive
    # 页面本体不再引用外部 CDN
    assert "cdn.tailwindcss.com" not in resp.text
    assert "/static/vendor/tailwindcss-play.js" in resp.text


def test_tailwind_play_vendor_served_locally(perfect_client):
    resp = perfect_client.get("/static/vendor/tailwindcss-play.js")
    assert resp.status_code == 200
    assert len(resp.content) > 100_000  # 451KB minified play bundle
    assert "tailwind" in resp.text[:100000].lower()
