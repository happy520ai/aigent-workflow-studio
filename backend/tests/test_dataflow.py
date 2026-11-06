# tests/test_dataflow.py —— A2：数据沿连线流动，上游输出注入下游 _inputs
import asyncio

from operator_registry import NeuralOperatorRegistry
from perfect_engine import ConnectionManager, PerfectNeuralEngine


def run(coro):
    return asyncio.run(coro)


def make_engine() -> PerfectNeuralEngine:
    return PerfectNeuralEngine(ws_manager=ConnectionManager())


def collect_inputs(eng: PerfectNeuralEngine, node_id: str) -> dict:
    return {
        e.source: eng.node_outputs.get(e.source)
        for e in eng.edges
        if e.target == node_id and e.source in eng.nodes
    }


def test_upstream_outputs_collected_as_inputs():
    eng = make_engine()
    eng.node_outputs["node_event_capturer"] = {"event_type": "CLICK"}

    inputs = collect_inputs(eng, "node_intent_agent")
    assert inputs == {"node_event_capturer": {"event_type": "CLICK"}}

    # 无上游输出时取到 None（首个节点）
    inputs_first = collect_inputs(eng, "node_event_capturer")
    assert inputs_first == {}


def test_logic_transform_normalized_keys_come_from_inputs():
    registry = NeuralOperatorRegistry()
    result = run(
        registry.execute(
            "logic_transform",
            {},
            {"bus_key": 1},
            inputs={"upstream_a": {}, "upstream_b": {}},
        )
    )
    assert result["output"]["normalized_keys"] == ["upstream_a", "upstream_b"]

    # 无上游时回退共享总线键
    result2 = run(registry.execute("logic_transform", {}, {"bus_key": 1}, inputs=None))
    assert result2["output"]["normalized_keys"] == ["bus_key"]


def test_fe_render_reports_upstream_keys():
    registry = NeuralOperatorRegistry()
    result = run(
        registry.execute(
            "fe_render",
            {},
            {},
            inputs={"node_agent_codegen": {"tsx": "..."}},
        )
    )
    assert result["output"]["upstream"] == ["node_agent_codegen"]


def test_execute_single_node_writes_output_for_downstream():
    eng = make_engine()

    async def scenario():
        await eng._execute_single_node(eng.nodes["node_event_capturer"])
        await eng._execute_single_node(eng.nodes["node_intent_agent"])

    run(scenario())
    output = eng.node_outputs.get("node_intent_agent")
    assert output is not None
    assert output["primary_intent"] == "GENERATE_REACTIVE_UI_COMPONENT"

    # 下游节点的 _inputs 能看到上游输出（经连线注入）
    assert collect_inputs(eng, "node_ui_gen")["node_intent_agent"] == output
