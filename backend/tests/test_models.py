# tests/test_models.py —— Pydantic v2 数据契约层单元测试
from models import (
    ComponentItem,
    ControlAction,
    ControlRequest,
    NeuralEdge,
    NodePosition,
    RadarMetrics,
    SystemTelemetry,
    WorkflowNode,
    WorkflowSnapshot,
    WorkflowStatus,
)


def test_workflow_status_enum_chinese_values():
    assert WorkflowStatus.IDLE.value == "已就绪"
    assert WorkflowStatus.RUNNING.value == "运行中"
    assert WorkflowStatus.PAUSED.value == "已暂停"
    assert WorkflowStatus.DEBUG.value == "调试中"
    assert WorkflowStatus.ERROR.value == "异常"


def test_control_action_enum_covers_four_buttons():
    assert {a.value for a in ControlAction} == {"run", "pause", "debug", "reset"}


def test_control_request_target_optional():
    req = ControlRequest(action=ControlAction.RUN)
    assert req.target_node_id is None
    req2 = ControlRequest(action="pause", target_node_id="node_ui_gen")
    assert req2.action is ControlAction.PAUSE
    assert req2.target_node_id == "node_ui_gen"


def test_node_position_roundtrip():
    pos = NodePosition(x=630, y=110)
    assert pos.model_dump() == {"x": 630.0, "y": 110.0}


def test_radar_metrics_five_dimension_defaults():
    r = RadarMetrics()
    assert r.radar_perception == 92.0
    assert r.responsiveness == 96.5
    assert r.accuracy == 99.2
    assert r.concurrency == 88.0
    assert r.stability == 95.4


def test_workflow_node_defaults():
    n = WorkflowNode(
        id="n1", type="t", title="标题", subtitle="(Sub)",
        position=NodePosition(x=1, y=2), theme_color="#fff",
        config_json={"k": "v"},
    )
    assert n.status == "idle"
    assert n.progress == 0.0
    assert n.confidence == 99.2
    assert n.latency_ms == 8


def test_neural_edge_defaults():
    e = NeuralEdge(id="e1", source="a", target="b")
    assert e.connection_status == "已连接"
    assert e.active_pulse is False
    assert e.latency_ms == 8
    assert e.confidence_pct == 99.2


def test_snapshot_contract_roundtrip():
    node = WorkflowNode(
        id="n1", type="t", title="T", subtitle="(T)",
        position=NodePosition(x=0, y=0), theme_color="#000", config_json={},
    )
    snap = WorkflowSnapshot(
        version="v3.0.0",
        project_status=WorkflowStatus.RUNNING,
        selected_node_id="n1",
        nodes=[node],
        edges=[],
        telemetry=SystemTelemetry(
            cpu_history=[1.0], memory_history=[2.0],
            ecg_waveform=[0.1], radar_metrics=RadarMetrics(),
        ),
        terminal_logs=["a", "b"],
    )
    data = snap.model_dump()
    assert data["version"] == "v3.0.0"
    assert data["project_status"] == "运行中"
    assert len(data["nodes"]) == 1
    # JSON 反序列化后恢复为强类型模型
    snap2 = WorkflowSnapshot.model_validate(data)
    assert snap2.nodes[0].id == "n1"
    assert snap2.telemetry.radar_metrics.accuracy == 99.2


def test_component_item_fields():
    c = ComponentItem(
        id="trig_events", category="触发器", category_en="Triggers",
        name="页面事件", name_en="Events", icon="Zap", theme_color="#10b981",
    )
    assert c.name_en == "Events"
    assert c.model_dump()["theme_color"] == "#10b981"
