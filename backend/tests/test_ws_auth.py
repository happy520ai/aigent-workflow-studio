# tests/test_ws_auth.py —— T11：WebSocket 握手鉴权
# 覆盖：未配置令牌放行（现有行为）、配置后 无/错/对 ?token=、
#       Sec-WebSocket-Protocol 子协议令牌、Origin 白名单（4403）、自定义关闭码 4401。
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from perfect_main import app

TOKEN = "ws-tok-123"


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def _recv_snapshot(ws):
    msg = ws.receive_json()
    assert msg["event"] == "workflow_snapshot"
    return msg


def test_ws_open_without_token_when_unset(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    with api.websocket_connect("/ws/telemetry") as ws:
        _recv_snapshot(ws)


def test_ws_requires_token_when_configured(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", TOKEN)
    # 无令牌 → 4401
    with pytest.raises(WebSocketDisconnect) as ei, api.websocket_connect("/ws/telemetry") as ws:
        ws.receive_json()
    assert ei.value.code == 4401
    # 错误令牌 → 4401
    with pytest.raises(WebSocketDisconnect) as ei:
        with api.websocket_connect("/ws/telemetry?token=wrong") as ws:
            ws.receive_json()
    assert ei.value.code == 4401


def test_ws_query_token_accepted(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", TOKEN)
    with api.websocket_connect(f"/ws/telemetry?token={TOKEN}") as ws:
        _recv_snapshot(ws)


def test_ws_subprotocol_token_accepted(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", TOKEN)
    with api.websocket_connect("/ws/telemetry", subprotocols=[TOKEN]) as ws:
        _recv_snapshot(ws)


def test_ws_origin_whitelist(api, monkeypatch):
    monkeypatch.delenv("AIGENT_ADMIN_TOKEN", raising=False)
    # 白名单内 Origin（默认 CORS_ORIGINS）→ 放行
    with api.websocket_connect(
        "/ws/telemetry", headers={"Origin": "http://localhost:5173"}
    ) as ws:
        _recv_snapshot(ws)
    # 非白名单 Origin → 4403
    with pytest.raises(WebSocketDisconnect) as ei, api.websocket_connect(
        "/ws/telemetry", headers={"Origin": "http://evil.example.com"}
    ) as ws:
        ws.receive_json()
    assert ei.value.code == 4403


def test_ws_origin_ok_but_bad_token_still_4401(api, monkeypatch):
    monkeypatch.setenv("AIGENT_ADMIN_TOKEN", TOKEN)
    with pytest.raises(WebSocketDisconnect) as ei, api.websocket_connect(
        "/ws/telemetry?token=wrong", headers={"Origin": "http://localhost:5173"}
    ) as ws:
        ws.receive_json()
    assert ei.value.code == 4401
