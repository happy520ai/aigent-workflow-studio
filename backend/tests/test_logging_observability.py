# tests/test_logging_observability.py —— T22：结构化日志 / X-Request-ID / 密钥过滤
import json
import logging

import pytest
from starlette.testclient import TestClient

from obs_logging import JsonFormatter, SecretFilter, configure_logging, redact_secrets
from perfect_main import app


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="aigent.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=message, args=(), exc_info=None,
    )


def test_secret_filter_redacts_known_shapes():
    secret = "sk-live-abcdef1234567890"
    filt = SecretFilter()
    rec = _record(f"calling llm with key {secret} via Bearer {secret} and X-Admin-Token: tok_abc123 plus /ws?token=ws-secret-99")
    assert filt.filter(rec) is True
    text = rec.getMessage()
    assert secret not in text
    assert "tok_abc123" not in text
    assert "ws-secret-99" not in text
    assert "***REDACTED***" in text


def test_secret_filter_redacts_current_admin_token(monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", "my-exact-admin-token-777")
    out = redact_secrets("auth failed for my-exact-admin-token-777 at 12:00")
    assert "my-exact-admin-token-777" not in out
    assert "***REDACTED***" in out


def test_json_formatter_emits_valid_json_with_context():
    formatter = JsonFormatter()
    rec = _record("hello world")
    line = formatter.format(rec)
    data = json.loads(line)
    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert "ts" in data and "logger" in data


def test_json_formatter_includes_request_id():
    from obs_logging import request_id_var

    formatter = JsonFormatter()
    token = request_id_var.set("rid-123456")
    try:
        data = json.loads(formatter.format(_record("with ctx")))
    finally:
        request_id_var.reset(token)
    assert data["request_id"] == "rid-123456"


def test_configure_logging_idempotent():
    configure_logging()
    handlers_before = list(logging.getLogger().handlers)
    configure_logging()
    assert logging.getLogger().handlers == handlers_before


def test_request_id_header_and_uniqueness(api):
    r1 = api.get("/healthz")
    r2 = api.get("/healthz")
    assert r1.headers.get("X-Request-ID")
    assert r2.headers.get("X-Request-ID")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_request_log_line_emitted(api, caplog):
    with caplog.at_level(logging.INFO, logger="aigent.api"):
        api.get("/healthz")
    http_logs = [r for r in caplog.records if r.msg.startswith("http_request")]
    assert http_logs, "请求日志未产生"
    assert "/healthz" in http_logs[-1].msg


def test_no_secret_in_request_logs(api, monkeypatch, caplog):
    # 全链路：配置令牌后 401 响应路径的日志不得含令牌字面值
    secret_token = "super-secret-e2e-token-42"
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", secret_token)
    with caplog.at_level(logging.INFO):
        api.post("/api/v1/workflow/edges", json={"source": "a", "target": "b"})
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_token not in blob
