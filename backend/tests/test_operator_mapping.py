# tests/test_operator_mapping.py —— A1：默认 5 个节点 type 经别名归一化后不再落入 _op_default
import asyncio

from operator_registry import _ALIASES, NeuralOperatorRegistry

DEFAULT_NODE_TYPES = [
    "event_capturer",
    "intent_agent",
    "ui_generation",
    "co_agent",
    "dom_renderer",
]


def run(coro):
    return asyncio.run(coro)


def test_default_node_types_resolve_via_aliases():
    registry = NeuralOperatorRegistry()
    bus: dict = {}
    for node_type in DEFAULT_NODE_TYPES:
        result = run(registry.execute(node_type, {}, bus))
        # 返回值标注归一化后的算子 key 与内置模拟模式
        assert result["operator"] == _ALIASES[node_type]
        assert result["mode"] == "simulated"
        # 未落入 _op_default（兜底算子的特征是 status="active" 且原样回显配置）
        assert result["status"] != "active"


def test_aliases_cover_all_five_types():
    assert _ALIASES == {
        "event_capturer": "trig_events",
        "intent_agent": "agent_intent",
        "ui_generation": "agent_codegen",
        "co_agent": "logic_state",
        "dom_renderer": "fe_render",
    }


def test_unknown_type_falls_back_to_default():
    registry = NeuralOperatorRegistry()
    cfg = {"custom": 1}
    result = run(registry.execute("unknown_xyz", cfg, {}))
    # 未知 type 保持原样走 _op_default：status="active" 且回显配置
    assert result["status"] == "active"
    assert result["output"]["custom"] == 1
    assert result["operator"] == "unknown_xyz"
    assert result["mode"] == "simulated"
