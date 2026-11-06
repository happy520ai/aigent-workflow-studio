# backend/operator_registry.py
import os
import re
import time
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

import httpx

from llm_client import LLMClient
from net_guard import IPPinnedTransport, resolve_and_pin_api_base


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

# T30：算子真实/模拟分类——mode 如实标注，不伪装
_REAL_OPERATORS = {"llm_generic", "http_request", "logic_transform"}


def _get_path(ctx: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    """按 a.b.0.c 点路径取值（支持 list 下标）；绝不 eval"""
    cur: Any = ctx
    for part in dotted.split("."):
        part = part.strip()
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return cur


_TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")


def _render_template(template: str, ctx: Dict[str, Any]) -> str:
    """{{a.b.c}} 模板渲染：点路径取值转字符串；无匹配占位符原样保留"""

    def _sub(m: "re.Match[str]") -> str:
        value = _get_path(ctx, m.group(1))
        return "" if value is None else str(value)

    return _TEMPLATE_RE.sub(_sub, template)


def _build_context(inputs: Dict[str, Any], bus: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """模板/映射上下文：共享总线 + 上游输出（保留 节点id 层 且平铺合并，最后者胜）+ 本节点配置"""
    ctx: Dict[str, Any] = dict(bus)
    for node_id, out in (inputs or {}).items():
        if isinstance(out, dict):
            ctx.update(out)
        ctx.setdefault(node_id, out)
    for key, value in cfg.items():
        if key != "_inputs":
            ctx[key] = value
    return ctx


class NeuralOperatorRegistry:
    """涵盖左侧组件库全部 6 大分组、12 个前端智能体算子的执行内核。

    T30：算子分为 real / simulated 两类并在输出 mode 字段如实标注——
    real：llm_generic（LLM 文本生成）、http_request（受 SSRF 防护的 HTTP 出站）、
          logic_transform（可配置点路径/模板映射，禁止 eval）。
    """

    def __init__(
        self,
        llm_config_provider: Optional[Callable[[], Dict[str, str]]] = None,
        llm_transport_factory: Optional[Callable[[], Any]] = None,
        http_transport_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._llm_config_provider = llm_config_provider
        self._llm_transport_factory = llm_transport_factory
        self._http_transport_factory = http_transport_factory  # 测试注入 MockTransport
        self._handlers: Dict[str, OperatorHandler] = {
            "trig_events": self._op_trig_events,
            "trig_schedule": self._op_trig_schedule,
            "perc_nlu": self._op_perc_nlu,
            "perc_vision": self._op_perc_vision,
            "agent_intent": self._op_agent_intent,
            "agent_codegen": self._op_agent_codegen,
            "llm_generic": self._op_llm_generic,
            "http_request": self._op_http_request,
            "logic_transform": self._op_logic_transform,
            "logic_state": self._op_logic_state,
            "fe_assemble": self._op_fe_assemble,
            "fe_render": self._op_fe_render,
            "dep_test": self._op_dep_test,
            "dep_publish": self._op_dep_publish,
        }

    def _resolve_mode(self, normalized: str) -> str:
        return "real" if normalized in _REAL_OPERATORS else "simulated"

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
        # 3. 如实标注归一化后的算子 key 与真实/模拟模式（T30）
        result["operator"] = normalized
        result["mode"] = self._resolve_mode(normalized)
        return result

    # ---- T30 真实算子公共件 ----
    def _llm_settings(self) -> Dict[str, str]:
        if self._llm_config_provider is not None:
            return dict(self._llm_config_provider())
        return {
            "api_key": os.getenv("LLM_API_KEY", "").strip(),
            "api_base": os.getenv("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/"),
            "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        }

    async def _pinned_transport_for_url(self, url: str) -> httpx.AsyncBaseTransport:
        """T30/T12：http_request 出站按已校验 IP 直连（用户自填 URL，IP 字面量也强校验）"""
        allow_private = os.getenv("AIGENT_ALLOW_PRIVATE_LLM", "") == "1"
        pinned_url = await resolve_and_pin_api_base(url, allow_private=allow_private, validate_ip_literals=True)
        return IPPinnedTransport(pinned_ip=httpx.URL(pinned_url).host)

    # T30 真实算子 ①：LLM 通用文本生成（system/user 模板，变量取自上游 _inputs）
    async def _op_llm_generic(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        ctx = _build_context(cfg.get("_inputs") or {}, bus, cfg)
        system_text = _render_template(str(cfg.get("system_template", "You are a helpful assistant.")), ctx)
        user_template = str(cfg.get("user_template", ""))
        user_text = _render_template(user_template, ctx) if user_template else str(ctx)[:500]
        llm_cfg = self._llm_settings()
        api_key = (llm_cfg.get("api_key") or "").strip()
        if not api_key:
            return {
                "status": "skipped_no_api_key",
                "confidence": 50.0,
                "output": {"reason": "LLM_API_KEY 未配置（真实算子不伪装输出）", "prompt": {"system": system_text, "user": user_text}},
            }
        client = LLMClient()
        result = await client.chat_completion(
            api_base=llm_cfg.get("api_base", "https://api.openai.com/v1"),
            api_key=api_key,
            model=str(cfg.get("model") or llm_cfg.get("model", "gpt-4o-mini")),
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            max_tokens=int(cfg.get("max_tokens", 1024)),
            transport_factory=self._llm_transport_factory,
        )
        if result["ok"]:
            bus["llm_generic_output"] = result["content"]
            return {"status": "completed", "confidence": 99.0, "output": {"text": result["content"], "attempts": result["attempts"]}}
        return {"status": "llm_failed", "confidence": 30.0, "degraded": True, "output": {"error": result["error"], "attempts": result["attempts"]}}

    # T30 真实算子 ②：HTTP 请求（SSRF 防护 + 响应体上限）
    _HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}

    async def _op_http_request(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        method = str(cfg.get("method", "GET")).upper()
        url = str(cfg.get("url", "")).strip()
        if method not in self._HTTP_METHODS:
            return {"status": "invalid_method", "confidence": 0.0, "output": {"error": f"method 仅允许 {sorted(self._HTTP_METHODS)}"}}
        if not (url.startswith("http://") or url.startswith("https://")):
            return {"status": "invalid_url", "confidence": 0.0, "output": {"error": "url 仅允许 http/https 且必须含主机名"}}
        timeout_s = float(cfg.get("timeout_s", 10))
        max_bytes = int(cfg.get("max_response_bytes", 64 * 1024))
        headers = {str(k): str(v) for k, v in (cfg.get("headers") or {}).items()}
        body = cfg.get("body")
        t0 = time.perf_counter()
        try:
            factory = self._http_transport_factory if self._http_transport_factory is not None else (lambda: self._pinned_transport_for_url(url))
            transport = await factory()
            async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False, transport=transport) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=body if isinstance(body, (dict, list)) else None,
                    content=body if isinstance(body, str) else None,
                )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            raw = resp.content
            truncated = len(raw) > max_bytes
            body_text = raw[:max_bytes].decode(resp.charset_encoding or "utf-8", errors="replace")
            out = {
                "status_code": resp.status_code,
                "elapsed_ms": round(elapsed_ms, 1),
                "truncated": truncated,
                "body": body_text,
            }
            bus["http_response"] = out
            return {"status": "completed" if resp.status_code < 400 else "http_error", "confidence": 99.0, "output": out}
        except ValueError as exc:  # SSRF 守卫拒绝（内网/保留地址/解析失败）
            return {"status": "blocked_by_ssrf_guard", "confidence": 0.0, "output": {"error": str(exc)}}
        except Exception as exc:
            return {"status": "request_failed", "confidence": 0.0, "output": {"error": str(exc)}}

    # T30 真实算子 ③：数据转换（可配置点路径/常量/模板映射，禁止 eval）
    async def _op_logic_transform(self, cfg: Dict[str, Any], bus: Dict[str, Any]) -> Dict[str, Any]:
        ctx = _build_context(cfg.get("_inputs") or {}, bus, cfg)
        mappings: List[Dict[str, Any]] = cfg.get("mappings") or []
        transformed: Dict[str, Any] = {}
        for m in mappings:
            target = str(m.get("target", "")).strip()
            if not target:
                continue
            if "value" in m:
                transformed[target] = m["value"]
            elif "source" in m:
                transformed[target] = _get_path(ctx, str(m["source"]), m.get("default"))
            elif "template" in m:
                transformed[target] = _render_template(str(m["template"]), ctx)
        if not mappings:
            # 向后兼容：未配置 mappings 时保留原归一化键清单行为
            upstream_inputs = cfg.get("_inputs") or {}
            transformed = {
                "normalized_keys": list(upstream_inputs.keys()) if upstream_inputs else list(bus.keys()),
                "schema_version": "v3-normalized",
            }
        bus["transformed_data"] = transformed
        return {"status": "transformed", "confidence": 99.5, "output": transformed}


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

    # 7. 数据逻辑 (Logic) -> 数据转换 (Transform)：真实实现见上方 _op_logic_transform（T30）

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
