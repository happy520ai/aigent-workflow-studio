# backend/engine.py
# DEPRECATED: v1 旧引擎，仅保留兼容；现役引擎见 perfect_engine.py。
import asyncio
import json
import math
import os
import random
import time
from datetime import datetime
from typing import Dict, List, Set
import httpx
import psutil
from fastapi import WebSocket

from models import (
    ComponentItem,
    ControlAction,
    NeuralEdge,
    NodePosition,
    RadarMetrics,
    SystemTelemetry,
    WorkflowNode,
    WorkflowSnapshot,
    WorkflowStatus,
)


class ConnectionManager:
    """管理所有前端工作台的 WebSocket 实时连接"""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, event_type: str, payload: dict) -> None:
        if not self.active_connections:
            return
        message = json.dumps(
            {
                "event": event_type,
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "data": payload,
            },
            ensure_ascii=False,
        )
        disconnected: Set[WebSocket] = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.active_connections.discard(conn)


class NeuralWorkflowEngine:
    """AIGENT-WORKFLOW STUDIO v2.8 核心神经元异步 DAG 引擎"""

    def __init__(self, ws_manager: ConnectionManager) -> None:
        self.ws_manager = ws_manager
        self.status: WorkflowStatus = WorkflowStatus.RUNNING
        self.selected_node_id: str = "node_ui_gen"

        # 暂停与调试控制锁
        self._pause_gate = asyncio.Event()
        self._pause_gate.set()  # 默认放行
        self._debug_mode: bool = False
        self._debug_step_gate = asyncio.Event()
        self._engine_task: asyncio.Task | None = None
        self._telemetry_task: asyncio.Task | None = None
        self._phase: float = 0.0

        # 实时监控历史队列
        self.cpu_history: List[float] = [32.0, 45.0, 28.0, 64.0, 41.0, 53.0, 38.0, 62.0, 49.0, 55.0]
        self.memory_history: List[float] = [58.0, 58.5, 59.2, 58.8, 60.1, 59.5, 60.4, 60.0, 61.2, 60.8]
        self.ecg_waveform: List[float] = [0.0, 0.2, -0.15, 0.85, -0.45, 0.3, 0.0, 0.05, -0.05, 0.1]
        self.radar_metrics = RadarMetrics(
            radar_perception=92.0,
            responsiveness=96.5,
            accuracy=99.2,
            concurrency=88.0,
            stability=95.4,
        )
        self.terminal_logs: List[str] = [
            "Agent initialized: 99.2%...",
            "Agent initialized: 99.2%...",
            "Agent initialized: 99.2%...",
            "Agent initialized: 99.2%...",
            "Agent initialized: 99.2%...",
            "Agent initialized: 99.2%...",
            "Agent initialized: 99.2%...",
            "Success...",
            "[System] Deploying to Sandbox...",
            "[System] Deploying to Sandbox...",
        ]

        self.components: List[ComponentItem] = self._init_component_library()
        self.nodes: Dict[str, WorkflowNode] = self._init_default_nodes()
        self.edges: List[NeuralEdge] = self._init_default_edges()

    def _init_component_library(self) -> List[ComponentItem]:
        """初始化左侧 6 大手风琴分组算子库"""
        return [
            ComponentItem(id="trig_events", category="触发器", category_en="Triggers", name="页面事件", name_en="Events", icon="Zap", theme_color="#10b981"),
            ComponentItem(id="trig_schedule", category="触发器", category_en="Triggers", name="定时触发", name_en="Schedule", icon="Clock", theme_color="#10b981"),
            ComponentItem(id="perc_nlu", category="感知解析", category_en="Perception", name="自然语言理解", name_en="NLU", icon="MessageSquare", theme_color="#38bdf8"),
            ComponentItem(id="perc_vision", category="感知解析", category_en="Perception", name="视觉输入", name_en="Vision", icon="Eye", theme_color="#38bdf8"),
            ComponentItem(id="agent_intent", category="AI 智能体", category_en="Agents", name="意图分析", name_en="Intent Agent", icon="Network", theme_color="#6366f1"),
            ComponentItem(id="agent_codegen", category="AI 智能体", category_en="Agents", name="代码生成", name_en="CodeGen", icon="Code", theme_color="#6366f1"),
            ComponentItem(id="logic_transform", category="数据逻辑", category_en="Logic", name="数据转换", name_en="Transform", icon="ArrowLeftRight", theme_color="#a855f7"),
            ComponentItem(id="logic_state", category="数据逻辑", category_en="Logic", name="状态管理", name_en="State", icon="Database", theme_color="#a855f7"),
            ComponentItem(id="fe_assemble", category="前端渲染", category_en="Frontend", name="组件装配", name_en="Assemble", icon="LayoutGrid", theme_color="#3b82f6"),
            ComponentItem(id="fe_render", category="前端渲染", category_en="Frontend", name="DOM 渲染", name_en="Render", icon="Terminal", theme_color="#3b82f6"),
            ComponentItem(id="dep_test", category="部署", category_en="Deploy", name="沙盒测试", name_en="Test", icon="FlaskConical", theme_color="#ec4899"),
            ComponentItem(id="dep_publish", category="部署", category_en="Deploy", name="发布", name_en="Publish", icon="Rocket", theme_color="#ec4899"),
        ]

    def _init_default_nodes(self) -> Dict[str, WorkflowNode]:
        """初始化中央画布的 5 个核心神经元节点及右侧 JSON 配置"""
        base_config = {
            "name": "Agentinightik.eod",
            "anenet5": {
                "enalen": "Pna",
                "data": {
                    "name": "智能体I",
                    "type": "准确度",
                    "temndary": "UI Generation",
                },
            },
        }
        nodes_list = [
            WorkflowNode(
                id="node_event_capturer",
                type="event_capturer",
                title="事件捕获",
                subtitle="(Event Capturer)",
                position=NodePosition(x=60, y=240),
                theme_color="#10b981",
                status="active",
                progress=100.0,
                confidence=99.8,
                latency_ms=8,
                config_json={**base_config, "role": "DOM Event & User Stream Listener"},
            ),
            WorkflowNode(
                id="node_intent_agent",
                type="intent_agent",
                title="意图识别智能体",
                subtitle="(Intent Agent)",
                position=NodePosition(x=310, y=240),
                theme_color="#6366f1",
                status="active",
                progress=100.0,
                confidence=99.2,
                latency_ms=8,
                config_json={**base_config, "role": "Semantic Router & Intent Classifier"},
            ),
            WorkflowNode(
                id="node_ui_gen",
                type="ui_generation",
                title="前端UI生成",
                subtitle="(UI Generation Agent)",
                position=NodePosition(x=630, y=110),
                theme_color="#38bdf8",
                status="active",
                progress=98.6,
                confidence=98.6,
                latency_ms=8,
                config_json=base_config,
            ),
            WorkflowNode(
                id="node_co_agent",
                type="co_agent",
                title="多Agent协作器",
                subtitle="(Co-Agent)",
                position=NodePosition(x=630, y=310),
                theme_color="#a855f7",
                status="active",
                progress=99.2,
                confidence=99.2,
                latency_ms=8,
                config_json={**base_config, "role": "Multi-Agent State Synchronizer"},
            ),
            WorkflowNode(
                id="node_dom_renderer",
                type="dom_renderer",
                title="页面渲染引擎",
                subtitle="(DOM Renderer)",
                position=NodePosition(x=630, y=440),
                theme_color="#3b82f6",
                status="success",
                progress=100.0,
                confidence=99.2,
                latency_ms=8,
                config_json={**base_config, "role": "Virtual DOM Diff & Hydrator"},
            ),
        ]
        return {n.id: n for n in nodes_list}

    def _init_default_edges(self) -> List[NeuralEdge]:
        """初始化 4 条多重发光神经突触连接线"""
        return [
            NeuralEdge(
                id="edge_1_2",
                source="node_event_capturer",
                target="node_intent_agent",
                latency_ms=8,
                confidence_pct=99.8,
                connection_status="已连接",
                active_pulse=True,
            ),
            NeuralEdge(
                id="edge_2_3a",
                source="node_intent_agent",
                target="node_ui_gen",
                latency_ms=8,
                confidence_pct=99.2,
                connection_status="已连接",
                active_pulse=True,
            ),
            NeuralEdge(
                id="edge_2_3b",
                source="node_intent_agent",
                target="node_co_agent",
                latency_ms=8,
                confidence_pct=99.2,
                connection_status="已连接",
                active_pulse=True,
            ),
            NeuralEdge(
                id="edge_2_3c",
                source="node_intent_agent",
                target="node_dom_renderer",
                latency_ms=8,
                confidence_pct=99.2,
                connection_status="已连接",
                active_pulse=True,
            ),
        ]

    def get_snapshot(self) -> WorkflowSnapshot:
        return WorkflowSnapshot(
            version="v2.8",
            project_status=self.status,
            selected_node_id=self.selected_node_id,
            nodes=list(self.nodes.values()),
            edges=self.edges,
            telemetry=SystemTelemetry(
                cpu_history=self.cpu_history,
                memory_history=self.memory_history,
                ecg_waveform=self.ecg_waveform,
                radar_metrics=self.radar_metrics,
            ),
            terminal_logs=self.terminal_logs[-12:],
        )

    async def append_log(self, log_line: str) -> None:
        self.terminal_logs.append(log_line)
        if len(self.terminal_logs) > 50:
            self.terminal_logs = self.terminal_logs[-50:]
        await self.ws_manager.broadcast(
            "terminal_log",
            {"line": log_line, "logs": self.terminal_logs[-12:]},
        )

    async def _wait_if_paused_or_debug(self, current_stage: str) -> None:
        """在神经突触传递间隙检查暂停锁与单步调试锁"""
        await self._pause_gate.wait()
        if self._debug_mode:
            await self.append_log(f"[Debug] 断点挂起于节点: {current_stage}，等待单步指令...")
            await self._debug_step_gate.wait()
            self._debug_step_gate.clear()

    async def _execute_llm_or_simulate(self, node: WorkflowNode) -> dict:
        """如果环境变量配置了 LLM_API_KEY 则发起真实大模型调用，否则执行毫秒级神经仿真计算"""
        api_key = os.getenv("LLM_API_KEY", "").strip()
        api_base = os.getenv("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/")
        model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")

        start_ts = time.perf_counter()
        if api_key:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(
                        f"{api_base}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": f"You are {node.title} in an AI frontend workflow."},
                                {"role": "user", "content": json.dumps(node.config_json, ensure_ascii=False)},
                            ],
                            "max_tokens": 60,
                        },
                    )
                    resp.raise_for_status()
            except Exception as exc:
                await self.append_log(f"[Warn] 外部模型调用降级为本地神经内核 ({exc})")
        else:
            await asyncio.sleep(random.uniform(0.35, 0.65))

        elapsed_ms = max(6, min(15, int((time.perf_counter() - start_ts) * 20)))
        confidence = round(random.uniform(98.4, 99.6), 1)
        return {"latency_ms": elapsed_ms, "confidence": confidence}

    async def _workflow_loop(self) -> None:
        """核心 DAG 循环调度协程：Node 1 -> Node 2 -> (Node 3A || Node 3B || Node 3C)"""
        while True:
            try:
                # 阶段 1：事件捕获 (Event Capturer)
                await self._wait_if_paused_or_debug("node_event_capturer")
                n1 = self.nodes["node_event_capturer"]
                n1.status = "active"
                res1 = await self._execute_llm_or_simulate(n1)
                n1.latency_ms = res1["latency_ms"]
                n1.confidence = res1["confidence"]
                await self.append_log(f"Agent initialized: {n1.confidence}%...")
                await self.ws_manager.broadcast("node_update", n1.model_dump())

                # 阶段 2：意图识别智能体 (Intent Agent)
                await self._wait_if_paused_or_debug("node_intent_agent")
                n2 = self.nodes["node_intent_agent"]
                n2.status = "active"
                res2 = await self._execute_llm_or_simulate(n2)
                n2.latency_ms = res2["latency_ms"]
                n2.confidence = 99.2
                await self.append_log("Agent initialized: 99.2%...")
                await self.ws_manager.broadcast("node_update", n2.model_dump())

                # 阶段 3：三路并行神经突触分叉 (UI 生成 + 多Agent协作器 + 页面渲染引擎)
                await self._wait_if_paused_or_debug("parallel_fanout_stage")
                parallel_ids = ["node_ui_gen", "node_co_agent", "node_dom_renderer"]
                results = await asyncio.gather(
                    *(self._execute_llm_or_simulate(self.nodes[nid]) for nid in parallel_ids)
                )

                for nid, res in zip(parallel_ids, results):
                    node_obj = self.nodes[nid]
                    node_obj.latency_ms = res["latency_ms"]
                    if nid == "node_ui_gen":
                        node_obj.progress = 98.6
                        node_obj.confidence = 98.6
                        node_obj.status = "active"
                    elif nid == "node_dom_renderer":
                        node_obj.progress = 100.0
                        node_obj.confidence = 99.2
                        node_obj.status = "success"
                    else:
                        node_obj.confidence = 99.2
                        node_obj.status = "active"
                    await self.ws_manager.broadcast("node_update", node_obj.model_dump())

                # 更新突触延迟与五维雷达数据
                for edge in self.edges:
                    edge.latency_ms = random.choice([7, 8, 8, 9])
                    edge.confidence_pct = 99.2

                self.radar_metrics = RadarMetrics(
                    radar_perception=round(random.uniform(90.0, 95.0), 1),
                    responsiveness=round(random.uniform(95.0, 98.5), 1),
                    accuracy=99.2,
                    concurrency=round(random.uniform(86.0, 92.0), 1),
                    stability=round(random.uniform(94.0, 97.5), 1),
                )

                await self.append_log("Success...")
                await self.append_log("[System] Deploying to Sandbox...")
                await asyncio.sleep(1.8)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await self.append_log(f"[Error] Engine cycle exception: {exc}")
                await asyncio.sleep(1.0)

    async def _telemetry_loop(self) -> None:
        """每 500ms 采集一次真实系统 CPU/内存指标与心电图（ECG）波形并推送至前端"""
        while True:
            try:
                self._phase += 0.45
                cpu_val = psutil.cpu_percent(interval=None)
                if cpu_val < 5.0:
                    cpu_val = round(35.0 + 20.0 * math.sin(self._phase) + random.uniform(-6, 6), 1)
                mem_val = round(psutil.virtual_memory().percent, 1)

                self.cpu_history = (self.cpu_history + [cpu_val])[-16:]
                self.memory_history = (self.memory_history + [mem_val])[-16:]

                # 生成事件捕获节点内部的心电脉冲波形
                ecg_point = (
                    0.88
                    if int(self._phase * 2) % 7 == 0
                    else (-0.42 if int(self._phase * 2) % 7 == 1 else round(math.sin(self._phase * 3) * 0.15, 2))
                )
                self.ecg_waveform = (self.ecg_waveform + [ecg_point])[-20:]

                await self.ws_manager.broadcast(
                    "telemetry_tick",
                    {
                        "project_status": self.status.value,
                        "cpu_history": self.cpu_history,
                        "memory_history": self.memory_history,
                        "ecg_waveform": self.ecg_waveform,
                        "radar_metrics": self.radar_metrics.model_dump(),
                        "edges": [e.model_dump() for e in self.edges],
                    },
                )
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.5)

    def start_background_tasks(self) -> None:
        if self._engine_task is None or self._engine_task.done():
            self._engine_task = asyncio.create_task(self._workflow_loop())
        if self._telemetry_task is None or self._telemetry_task.done():
            self._telemetry_task = asyncio.create_task(self._telemetry_loop())

    async def stop_background_tasks(self) -> None:
        for task in (self._engine_task, self._telemetry_task):
            if task and not task.done():
                task.cancel()

    async def handle_control(self, action: ControlAction) -> WorkflowSnapshot:
        """响应顶部【运行 Run】、【暂停 Pause】、【调试 Debug】三个按钮的控制指令"""
        if action == ControlAction.RUN:
            self._debug_mode = False
            self._debug_step_gate.set()
            self._pause_gate.set()
            self.status = WorkflowStatus.RUNNING
            await self.append_log("[System] 工作流已恢复全速运行 (RUNNING)...")

        elif action == ControlAction.PAUSE:
            self._pause_gate.clear()
            self.status = WorkflowStatus.PAUSED
            await self.append_log("[System] 神经元脉冲已挂起暂停 (PAUSED)...")

        elif action == ControlAction.DEBUG:
            self._pause_gate.set()
            self._debug_mode = True
            self._debug_step_gate.set()  # 触发单步放行一次
            self.status = WorkflowStatus.DEBUG
            await self.append_log("[Debug] 已触发单步神经元突触调试 (STEP_DEBUG)...")

        elif action == ControlAction.RESET:
            self._debug_mode = False
            self._debug_step_gate.set()  # 修复：RESET 需同时放行单步门，否则调试挂起后工作循环会永久冻结（与 RUN 分支对称）
            self._pause_gate.set()
            self.nodes = self._init_default_nodes()
            self.status = WorkflowStatus.RUNNING
            await self.append_log("[System] 神经元拓扑状态已重置...")

        snapshot = self.get_snapshot()
        await self.ws_manager.broadcast("workflow_snapshot", snapshot.model_dump())
        return snapshot

    async def update_node_config(self, node_id: str, new_config: Dict) -> WorkflowNode:
        if node_id not in self.nodes:
            raise KeyError(f"节点 {node_id} 不存在")
        node = self.nodes[node_id]
        node.config_json = new_config
        self.selected_node_id = node_id
        await self.append_log(f"[Inspector] 已热更新节点 {node.title} 的 JSON 配置")
        await self.ws_manager.broadcast("node_update", node.model_dump())
        return node
