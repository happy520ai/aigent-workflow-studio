# tests/test_settings_guard.py —— A6(c)：LLM 设置接口守卫 + SSRF 校验 + 不回显密钥
import pytest
from starlette.testclient import TestClient

from perfect_main import app

DEFAULT_CFG = {"api_key": "", "api_base": "https://api.openai.com/v1", "model": "gpt-4o-mini"}


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c
    # 恢复全局引擎配置，避免影响其他测试（LLM 分支按 api_key 判定是否真实外呼）
    from perfect_main import engine

    engine.llm_config = dict(DEFAULT_CFG)


def test_admin_token_required_when_configured(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "secret-token")
    payload = {"api_key": "", "api_base": "https://api.openai.com/v1", "model": "m1"}

    # 无令牌 → 401
    r = api.put("/api/v1/settings/llm", json=payload)
    assert r.status_code == 401
    # 错误令牌 → 401
    r = api.put("/api/v1/settings/llm", json=payload, headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 401
    # 正确令牌 → 200（allowlist 跳过 DNS）
    monkeypatch.setenv("LLM_API_BASE_ALLOWLIST", "api.openai.com")
    r = api.put("/api/v1/settings/llm", json=payload, headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 200

    # GET 同样要求令牌
    r = api.get("/api/v1/settings/llm")
    assert r.status_code == 401
    r = api.get("/api/v1/settings/llm", headers={"X-Admin-Token": "secret-token"})
    assert r.status_code == 200


def test_ssrf_targets_rejected(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("LLM_API_BASE_ALLOWLIST", "")  # 走 DNS 解析校验路径

    # 云元数据地址（link-local）
    r = api.put(
        "/api/v1/settings/llm",
        json={"api_key": "", "api_base": "http://169.254.169.254/", "model": "m"},
    )
    assert r.status_code == 400

    # 本机回环
    r = api.put(
        "/api/v1/settings/llm",
        json={"api_key": "", "api_base": "http://127.0.0.1:9/", "model": "m"},
    )
    assert r.status_code == 400

    # 非 http 协议
    r = api.put(
        "/api/v1/settings/llm",
        json={"api_key": "", "api_base": "ftp://example.com/v1", "model": "m"},
    )
    assert r.status_code == 400


def test_response_never_echoes_api_key(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("LLM_API_BASE_ALLOWLIST", "api.openai.com")

    secret = "sk-abcdef123456"
    r = api.put(
        "/api/v1/settings/llm",
        json={"api_key": secret, "api_base": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    )
    assert r.status_code == 200
    assert secret not in r.text

    g = api.get("/api/v1/settings/llm")
    assert g.status_code == 200
    data = g.json()
    assert data["has_key"] is True
    assert data["key_hint"] == "sk-****3456"
    assert secret not in g.text
