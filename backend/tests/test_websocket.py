# tests/test_websocket.py —— /ws/telemetry 实时通道集成测试
import json
import time


def recv_until(ws, event_name, timeout_s=6.0):
    """持续接收直到拿到目标事件（中间会穿插遥测节拍等其他事件）"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        msg = json.loads(ws.receive_text())
        if msg.get("event") == event_name:
            return msg
    raise AssertionError(f"超时未收到事件 {event_name}")


def test_ws_initial_snapshot_then_telemetry_and_selection(client):
    with client.websocket_connect("/ws/telemetry") as ws:
        # 1) 连接即下发完整快照
        snap_msg = recv_until(ws, "workflow_snapshot")
        data = snap_msg["data"]
        assert data["version"] == "v2.8"
        assert len(data["nodes"]) == 5

        # 2) 遥测节拍：CPU/内存历史 + 心电波形 + 雷达 + 突触连线
        tick = recv_until(ws, "telemetry_tick")
        td = tick["data"]
        assert 10 <= len(td["cpu_history"]) <= 16
        assert 10 <= len(td["memory_history"]) <= 16
        assert len(td["ecg_waveform"]) == 20
        assert len(td["edges"]) == 4
        assert td["project_status"] in {"已就绪", "运行中", "已暂停", "调试中", "异常"}

        # 3) 前端选中节点指令 → 服务端回执
        ws.send_json({"type": "select_node", "node_id": "node_intent_agent"})
        sel = recv_until(ws, "selected_node_changed")
        assert sel["data"]["id"] == "node_intent_agent"

        # 4) 引擎循环持续产出终端日志事件
        log = recv_until(ws, "terminal_log")
        assert isinstance(log["data"]["line"], str)
        assert len(log["data"]["logs"]) <= 12


def test_ws_select_unknown_node_is_ignored(client):
    with client.websocket_connect("/ws/telemetry") as ws:
        recv_until(ws, "workflow_snapshot")
        ws.send_json({"type": "select_node", "node_id": "node_ghost"})
        # 非法选中不会回执；通道继续收到遥测即代表连接未被中断
        tick = recv_until(ws, "telemetry_tick")
        assert tick["event"] == "telemetry_tick"
