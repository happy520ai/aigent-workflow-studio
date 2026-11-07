# tests/test_production_guard.py —— T62：AIGENT_ENV=production 缺失必填配置则启动失败
import pytest
from starlette.testclient import TestClient

from perfect_main import app


def test_production_requires_token_and_allowlist(monkeypatch):
    monkeypatch.setenv("AIGENT_ENV", "production")
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("LLM_API_BASE_ALLOWLIST", raising=False)
    with pytest.raises(RuntimeError, match="缺少必需配置"):
        with TestClient(app):
            pass  # lifespan 进入即应失败


def test_production_starts_with_full_config(monkeypatch):
    monkeypatch.setenv("AIGENT_ENV", "production")
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "prod-token")
    monkeypatch.setenv("LLM_API_BASE_ALLOWLIST", "api.openai.com")
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        # 令牌已生效：无头访问敏感面被拒
        assert client.get("/api/v1/settings/llm").status_code == 401


def test_development_env_skips_guard(monkeypatch):
    monkeypatch.delenv("AIGENT_ENV", raising=False)
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
