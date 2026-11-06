# backend/operator_registry.py
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, Optional


OperatorHandler = Callable[[Dict[str, Any], Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]

# 画布节点 type（前端 1:1 命名）到注册表内部算子 key 的别名归一化表：
# 默认 5 个节点的 type 使用的英文名与 _handlers 的 key 不一致，execute 前必须先归一化，
# 否则会全部落入 _op_default 兜底算子。
_ALIASES: Dict[str, str] = {
    "event_capturer": "trig_events",
    "intent_agent": "agent_intent",
    "ui_generation": "agent_codegen",
    "co_agent": "logic_state",
    "dom_renderer": "fe_render",
}


class NeuralOperatorRegistry:
    """涵盖左侧组件库全部 6 大分组、12 个前端智能体算子的真实执行内核"""

    def __init__(self) -> None:
        self._handlers: Dict[str, OperatorHandler] = {
            "trig_events": self._op_trig_events,
            "trig_schedule": self._op_trig_schedule,
            "perc_nlu": self._op_perc_nlu,
            "perc_vision": self._op_perc_vision,
            "agent_intent": self._op_agent_intent,
            "agent_codegen": self._op_agent_codegen,
            "logic_transform": self._op_logic_transform,
            "logic_state": self._op_logic_state,
            "fe_assemble": self._op_fe_assemble,
            "fe_render": self._op_fe_render,
            "dep_test": self._op_dep_test,
            "dep_publish": self._op_dep_publish,
        }

    async def execute(
        self,
        operator_type: str,
        node_config: Dict[str, Any],
        shared_bus: Dict[str, Any],
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # 1. 别名归一化：画布节点 type -> 注册表算子 key；未知 type 保持原样落入 _op_default
        normalized = _ALIASES.get(operator_type, operator_type)
        handler = self._handlers.get(normalized, self._op_default)
        # 2. 上游输出注入配置副本（各 _op_* 签名不变，通过 cfg["_inputs"] 消费）
        cfg = {**node_config, "_inputs": inputs}
        result = await handler(cfg, shared_bus)
        # 3. 如实标注归一化后的算子 key 与内置模拟模式（当前算子为内置模拟，非真实推理）
        result["operator"] = normalized
        result["mode"] = "simulated"
        return result

    # 1. 触发器 (Triggers) -> 页面事件 (Events)
    async def _op_trig_events(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        event_payload = {
            "event_type": "DOM_INTERACTION_STREAM",
            "target_selector": cfg.get("selector", "#aigent-workbench-root"),
            "captured_at": datetime.now().isoformat(),
        }
        bus["trigger_event"] = event_payload
        return {"status": "triggered", "confidence": 99.8, "output": event_payload}

    # 2. 触发器 (Triggers) -> 定时触发 (Schedule)
    async def _op_trig_schedule(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        cron_expr = cfg.get("cron", "*/5 * * * * *")
        bus["schedule_tick"] = {"cron": cron_expr, "tick_ts": datetime.now().isoformat()}
        return {"status": "scheduled", "confidence": 99.9, "output": bus["schedule_tick"]}

    # 3. 感知解析 (Perception) -> 自然语言理解 (NLU)
    async def _op_perc_nlu(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        tokens = ["构建", "赛博神经元", "前端监控卡片", "带实时波形"]
        nlu_result = {"intent_tokens": tokens, "sentiment": "directive", "embedding_dim": 1536}
        bus["nlu_context"] = nlu_result
        return {"status": "parsed", "confidence": 99.2, "output": nlu_result}

    # 4. 感知解析 (Perception) -> 视觉输入 (Vision)
    async def _op_perc_vision(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        vision_layout = {
            "detected_regions": ["TopNavbar", "LeftSidebar", "NeuralCanvas", "RightInspector"],
            "dominant_palette": ["#070a12", "#10b981", "#38bdf8", "#a855f7"],
        }
        bus["vision_context"] = vision_layout
        return {"status": "analyzed", "confidence": 98.9, "output": vision_layout}

    # 5. AI 智能体 (Agents) -> 意图分析 (Intent Agent)
    async def _op_agent_intent(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        routing = {
            "primary_intent": "GENERATE_REACTIVE_UI_COMPONENT",
            "fanout_targets": ["node_ui_gen", "node_co_agent", "node_dom_renderer"],
            "confidence_score": 99.2,
        }
        bus["intent_routing"] = routing
        return {"status": "routed", "confidence": 99.2, "output": routing}

    # 6. AI 智能体 (Agents) -> 代码生成 (CodeGen)
    async def _op_agent_codegen(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        component_name = cfg.get("name", "AgentTelemetryCard").replace(".", "_")
        generated_tsx = f"""export const {component_name} = () => (
  <div className="p-4 rounded-xl bg-slate-900/90 border border-cyan-500/40 text-slate-100">
    <div className="text-xs text-cyan-400 font-mono">⚡ {component_name}</div>
    <div className="text-sm font-bold mt-1">突触延迟: 8ms | 准确度: 99.2%</div>
  </div>
);"""
        bus["generated_tsx"] = generated_tsx
        return {"status": "generated", "confidence": 98.6, "output": {"tsx": generated_tsx}}

    # 7. 数据逻辑 (Logic) -> 数据转换 (Transform)
    async def _op_logic_transform(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        # 归一化键优先来自上游节点的输出（数据真正沿连线流动），无上游时回退共享总线
        upstream_inputs = cfg.get("_inputs") or {}
        transformed = {
            "normalized_keys": list(upstream_inputs.keys()) if upstream_inputs else list(bus.keys()),
            "schema_version": "v2.8-normalized",
        }
        bus["transformed_data"] = transformed
        return {"status": "transformed", "confidence": 99.5, "output": transformed}

    # 8. 数据逻辑 (Logic) -> 状态管理 (State)
    async def _op_logic_state(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        store_slice = {
            "store_engine": "Zustand_Neural_Slice",
            "hydration_state": "SYNCHRONIZED",
            "keys_count": len(bus),
        }
        bus["state_store"] = store_slice
        return {"status": "synced", "confidence": 99.4, "output": store_slice}

    # 9. 前端渲染 (Frontend) -> 组件装配 (Assemble)
    async def _op_fe_assemble(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        upstream_inputs = cfg.get("_inputs") or {}
        bundle = {
            "imports": ["React", "lucide-react", "TailwindCSS"],
            "tree_shaking": True,
            "chunk_size_kb": 14.2,
            "upstream": list(upstream_inputs.keys()),
        }
        bus["assembled_bundle"] = bundle
        return {"status": "assembled", "confidence": 99.1, "output": bundle}

    # 10. 前端渲染 (Frontend) -> DOM 渲染 (Render)
    async def _op_fe_render(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        upstream_inputs = cfg.get("_inputs") or {}
        render_stats = {
            "vdom_diff_ms": 1.8,
            "hydration_ms": 6.2,
            "total_latency_ms": 8,
            "status_badge": "Success",
            "upstream": list(upstream_inputs.keys()),
        }
        bus["dom_render_metrics"] = render_stats
        return {"status": "success", "confidence": 99.2, "output": render_stats}

    # 11. 部署 (Deploy) -> 沙盒测试 (Test)
    async def _op_dep_test(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        test_report = {
            "unit_tests_passed": 18,
            "xss_sanitized": True,
            "sandbox_env": "ShadowDOM_Isolated",
        }
        bus["sandbox_test_report"] = test_report
        return {"status": "passed", "confidence": 99.6, "output": test_report}

    # 12. 部署 (Deploy) -> 发布 (Publish)
    async def _op_dep_publish(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        publish_meta = {
            "cdn_edge_nodes": 12,
            "release_tag": f"v2.8.{datetime.now().strftime('%H%M%S')}",
            "live_url": "/api/v1/publish/live-app",
        }
        bus["publish_receipt"] = publish_meta
        return {"status": "published", "confidence": 99.9, "output": publish_meta}

    async def _op_default(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "active", "confidence": 99.2, "output": cfg}
