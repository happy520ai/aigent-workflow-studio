# backend/perfect_engine.py
import asyncio
import json
import math
import os
import random
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import httpx
import psutil
from fastapi import WebSocket

from ast_validator import FrontendASTValidator
from llm_client import LLMClient
from net_guard import IPPinnedTransport, resolve_and_pin_api_base  # T12 工具再导出（兼容既有导入方）
from metrics import metrics
from obs_logging import get_logger
from models import (
    ComponentItem,
    ControlAction,
    NeuralEdge,
    NodePosition,    RadarMetrics,
    SystemTelemetry,
    WorkflowNode,
    WorkflowSnapshot,
    WorkflowStatus,
)
from operator_registry import NeuralOperatorRegistry

logger = get_logger("aigent.engine")


# ======================= T21：SQLite 稳健化（P2 可靠性） =======================
def sqlite_connect(db_path: str) -> sqlite3.Connection:
    """统一连接入口：WAL（读写并发友好）+ synchronous=NORMAL（崩溃安全与性能平衡）+
    busy_timeout=5000（写锁短暂争用时等待而非立刻报错）。"""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# 写入串行化：checkpoint 写、拓扑写、运行记录写（T26）共用一把进程内锁，
# 配合 WAL 避免多 to_thread 并发写时的 SQLITE_BUSY 与交错提交。
SQLITE_WRITE_LOCK = threading.Lock()


class CheckpointStore:
    """基于 SQLite 的神经元时间旅行断点持久化存储引擎"""

    # 断点库上限：超出后按时间倒序剪枝，防止长时间运行撑爆磁盘
    CHECKPOINT_MAX = int(os.getenv("CHECKPOINT_MAX", "2000"))
    # T21：schema 版本。v1=基线（checkpoints+topology）；v2=补 topology_json 列；
    # v3=runs 运行记录持久化表（T26，重启不丢）；v4=workflows 多工作流表 + checkpoints.workflow_id（T32）
    SCHEMA_VERSION = 4

    def __init__(self, db_path: Optional[str] = None) -> None:
        # db_path 缺省时优先取环境变量 AIGENT_DB_PATH，再回落到工作目录默认库
        self.db_path = db_path or os.getenv("AIGENT_DB_PATH") or "aigent_checkpoints.db"
        self._init_db()

    def _migrate(self, conn: sqlite3.Connection, current: int) -> None:
        """T21：显式迁移函数（替换散落的 ALTER TABLE），每步幂等，可对旧库重复执行"""
        # v0 → v1：基线表
        if current < 1:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    state_payload TEXT NOT NULL,
                    generated_code TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topology (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    nodes_json TEXT NOT NULL,
                    edges_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        # v1 → v2：旧库补 topology_json 列（幂等：列存在则跳过）
        if current < 2:
            existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(checkpoints)").fetchall()]
            if "topology_json" not in existing_cols:
                conn.execute("ALTER TABLE checkpoints ADD COLUMN topology_json TEXT DEFAULT ''")
        # v2 → v3：runs 运行记录持久化表（T26）
        if current < 3:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    round_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    nodes_json TEXT NOT NULL
                )
                """
            )
        # v2 → v4：workflows 多工作流表 + checkpoints.workflow_id（T32）
        if current < 4:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    nodes_json TEXT NOT NULL,
                    edges_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            ckpt_cols = [r[1] for r in conn.execute("PRAGMA table_info(checkpoints)").fetchall()]
            if "workflow_id" not in ckpt_cols:
                conn.execute("ALTER TABLE checkpoints ADD COLUMN workflow_id TEXT DEFAULT ''")

    def _init_db(self) -> None:
        with SQLITE_WRITE_LOCK:
            with sqlite_connect(self.db_path) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
                row = conn.execute("SELECT version FROM schema_version").fetchone()
                current = int(row[0]) if row else 0
                self._migrate(conn, current)
                if row:
                    conn.execute("UPDATE schema_version SET version = ?", (self.SCHEMA_VERSION,))
                else:
                    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
                conn.commit()

    async def save_checkpoint(
        self,
        run_id: str,
        node_id: str,
        state_payload: Dict[str, Any],
        generated_code: str,
        topology: Optional[Dict[str, Any]] = None,
        workflow_id: str = "",
    ) -> str:
        checkpoint_id = f"ckpt_{uuid.uuid4().hex[:8]}"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        payload_str = json.dumps(state_payload, ensure_ascii=False)
        topology_str = json.dumps(topology, ensure_ascii=False) if topology else ""

        def _insert() -> None:
            with SQLITE_WRITE_LOCK:  # T21：写串行化
                with sqlite_connect(self.db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO checkpoints
                            (checkpoint_id, run_id, node_id, timestamp, state_payload, generated_code, topology_json, workflow_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (checkpoint_id, run_id, node_id, ts, payload_str, generated_code, topology_str, workflow_id),
                    )
                    # 断点剪枝：只保留最近 CHECKPOINT_MAX 条
                    conn.execute(
                        """
                        DELETE FROM checkpoints WHERE checkpoint_id NOT IN
                        (SELECT checkpoint_id FROM checkpoints ORDER BY timestamp DESC LIMIT ?)
                        """,
                        (self.CHECKPOINT_MAX,),
                    )
                    conn.commit()

        await asyncio.to_thread(_insert)
        return checkpoint_id

    async def list_checkpoints(self, limit: int = 20) -> List[Dict[str, Any]]:
        def _query() -> List[Dict[str, Any]]:
            with sqlite_connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM checkpoints ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                # 键集合保持原有 6 个（不暴露 topology_json，契约不变）
                return [
                    {
                        "checkpoint_id": r["checkpoint_id"],
                        "run_id": r["run_id"],
                        "node_id": r["node_id"],
                        "timestamp": r["timestamp"],
                        "state_payload": json.loads(r["state_payload"]),
                        "generated_code": r["generated_code"],
                    }
                    for r in rows
                ]

        return await asyncio.to_thread(_query)

    async def save_run(
        self,
        round_id: str,
        run_id: str,
        started_at: str,
        finished_at: str,
        status: str,
        nodes: List[Dict[str, Any]],
    ) -> None:
        """T26：持久化一轮 DAG 运行记录（重启后 /api/v1/runs 仍有数据）"""
        nodes_str = json.dumps(nodes, ensure_ascii=False)

        def _insert() -> None:
            with SQLITE_WRITE_LOCK:
                with sqlite_connect(self.db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO runs (round_id, run_id, started_at, finished_at, status, nodes_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(round_id) DO UPDATE SET
                            run_id = excluded.run_id,
                            started_at = excluded.started_at,
                            finished_at = excluded.finished_at,
                            status = excluded.status,
                            nodes_json = excluded.nodes_json
                        """,
                        (round_id, run_id, started_at, finished_at, status, nodes_str),
                    )
                    # 只保留最近 50 轮
                    conn.execute(
                        """
                        DELETE FROM runs WHERE round_id NOT IN
                        (SELECT round_id FROM runs ORDER BY finished_at DESC LIMIT 50)
                        """
                    )
                    conn.commit()

        await asyncio.to_thread(_insert)

    # ======================= T32：多工作流持久化 CRUD =======================
    async def save_workflow(self, workflow_id: str, name: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
        nodes_str = json.dumps(nodes, ensure_ascii=False)
        edges_str = json.dumps(edges, ensure_ascii=False)

        def _upsert() -> None:
            with SQLITE_WRITE_LOCK:
                with sqlite_connect(self.db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO workflows (id, name, nodes_json, edges_json, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name = excluded.name,
                            nodes_json = excluded.nodes_json,
                            edges_json = excluded.edges_json,
                            updated_at = excluded.updated_at
                        """,
                        (workflow_id, name, nodes_str, edges_str, datetime.now().isoformat()),
                    )
                    conn.commit()

        await asyncio.to_thread(_upsert)

    async def list_workflows(self) -> List[Dict[str, Any]]:
        def _query() -> List[Dict[str, Any]]:
            with sqlite_connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, name, updated_at FROM workflows ORDER BY updated_at DESC"
                ).fetchall()
                return [dict(r) for r in rows]

        return await asyncio.to_thread(_query)

    async def get_workflow_row(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        def _query() -> Optional[Dict[str, Any]]:
            with sqlite_connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM workflows WHERE id = ?",
                    (workflow_id,),
                ).fetchone()
                if row is None:
                    return None
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "nodes": json.loads(row["nodes_json"]),
                    "edges": json.loads(row["edges_json"]),
                    "updated_at": row["updated_at"],
                }

        return await asyncio.to_thread(_query)

    async def delete_workflow_row(self, workflow_id: str) -> bool:
        def _delete() -> bool:
            with SQLITE_WRITE_LOCK:
                with sqlite_connect(self.db_path) as conn:
                    cur = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
                    conn.commit()
                    return cur.rowcount > 0

        return await asyncio.to_thread(_delete)

    async def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """T26：按时间倒序读运行记录（与内存 run_history 行结构兼容：round_id/started_at/finished_at/nodes）"""

        def _query() -> List[Dict[str, Any]]:
            with sqlite_connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY finished_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [
                    {
                        "round_id": r["round_id"],
                        "run_id": r["run_id"],
                        "started_at": r["started_at"],
                        "finished_at": r["finished_at"],
                        "status": r["status"],
                        "nodes": json.loads(r["nodes_json"]),
                    }
                    for r in rows
                ]

        return await asyncio.to_thread(_query)

    async def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """按 id 精确取回断点完整行（含 topology_json），不再受 list 窗口限制"""

        def _query() -> Optional[Dict[str, Any]]:
            with sqlite_connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                ).fetchone()
                if row is None:
                    return None
                return {
                    "checkpoint_id": row["checkpoint_id"],
                    "run_id": row["run_id"],
                    "node_id": row["node_id"],
                    "timestamp": row["timestamp"],
                    "state_payload": json.loads(row["state_payload"]),
                    "generated_code": row["generated_code"],
                    "topology_json": json.loads(row["topology_json"]) if row["topology_json"] else None,
                    "workflow_id": row["workflow_id"] if "workflow_id" in row.keys() else "",
                }

        return await asyncio.to_thread(_query)


class ConnectionManager:
    """全双工 WebSocket 神经突触广播中心"""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, accept: bool = True) -> None:
        # accept=False 供端点先完成握手并鉴权后登记连接（T11 WS 鉴权）
        if accept:
            await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, event_type: str, payload: Any) -> None:
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
        dead: Set[WebSocket] = set()
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active_connections.discard(ws)


@dataclass
class WorkflowState:
    """T32：单个工作流的隔离状态（节点/连线/总线/输出/运行记录/断点游标）"""

    nodes: Dict[str, "WorkflowNode"] = field(default_factory=dict)
    edges: List["NeuralEdge"] = field(default_factory=list)
    shared_memory_bus: Dict[str, Any] = field(
        default_factory=lambda: {
            "last_event": "USER_CLICK_GENERATE_DASHBOARD",
            "intent": "create_cyber_analytics_card",
            "co_agent_review": "PASS_WITH_99.2%_CONFIDENCE",
            "dom_hydration_status": "READY",
        }
    )
    node_outputs: Dict[str, Any] = field(default_factory=dict)
    run_history: deque = field(default_factory=lambda: deque(maxlen=20))
    recent_executions: deque = field(default_factory=lambda: deque(maxlen=50))
    selected_node_id: str = "node_ui_gen"
    current_run_id: str = ""
    latest_sandbox_html: str = ""
    round_seq: int = 0
    cycle_layer_hit: bool = False


class PerfectNeuralEngine:
    """集成动态 DAG 拓扑编译、12 算子内核、AST 自动自愈与 SQLite 时间旅行的终极引擎。

    T32：引擎承载多个工作流（WorkflowState），所有既有属性（nodes/edges/shared_memory_bus…）
    以 property 委托到「当前激活」工作流——存量代码零改动即可工作，多工作流按 id 隔离。
    """

    DEFAULT_WORKFLOW_ID = "default"

    def __init__(self, ws_manager: ConnectionManager, persist_topology: bool = False) -> None:
        self.ws_manager = ws_manager
        self.persist_topology = persist_topology
        self.checkpoint_store = CheckpointStore()
        # T30：真实算子（llm_generic 等）经 provider 读取运行时 LLM 配置（设置面板热更新即时生效）
        self.operator_registry = NeuralOperatorRegistry(llm_config_provider=lambda: self.llm_config)
        self.status: WorkflowStatus = WorkflowStatus.RUNNING

        # 运行时大模型配置（可通过前端设置面板动态热更新）
        self.llm_config: Dict[str, str] = {
            "api_key": os.getenv("LLM_API_KEY", "").strip(),
            "api_base": os.getenv("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/"),
            "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        }

        self._pause_gate = asyncio.Event()
        self._pause_gate.set()
        self._debug_mode: bool = False
        self._debug_step_gate = asyncio.Event()

        # T32：多工作流状态容器与激活指针
        self._workflows: Dict[str, WorkflowState] = {}
        self.active_workflow_id: str = self.DEFAULT_WORKFLOW_ID
        self._workflows[self.DEFAULT_WORKFLOW_ID] = WorkflowState(
            current_run_id=f"run_{uuid.uuid4().hex[:6]}",
            latest_sandbox_html=self._default_sandbox_template("初始化智能体监控面板 v2.8"),
        )

        # T27：ECG 波形的数据源改为真实指标——最近一轮 DAG 总耗时（ms），遥测每 0.5s 归一化采样
        self.last_round_latency_ms: float = 0.0

        self._engine_task: Optional[asyncio.Task] = None
        self._telemetry_task: Optional[asyncio.Task] = None
        self._phase: float = 0.0
        # T20/T25：健康看护——最近一次心跳（time.monotonic）与两个循环的连续失败计数
        self.last_tick_monotonic: Optional[float] = None
        self.loop_failure_counts: Dict[str, int] = {"dag": 0, "telemetry": 0}

        self.cpu_history: List[float] = [32.0, 45.0, 28.0, 64.0, 41.0, 53.0, 38.0, 62.0, 49.0, 55.0]
        self.memory_history: List[float] = [58.0, 58.5, 59.2, 58.8, 60.1, 59.5, 60.4, 60.0, 61.2, 60.8]
        self.ecg_waveform: List[float] = [0.0] * 10  # T27：真实指标初始为平线（无轮次数据）
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

        self.components: List[ComponentItem] = self._init_components()
        self.nodes = self._init_nodes()  # 经 property 写入激活工作流
        self.edges = self._init_edges()

        # 拓扑持久化：启动时从 SQLite workflows 表还原（旧 topology 表自动迁移为 default）
        if self.persist_topology:
            self._load_topology_sync()

    # ======================= T32：激活工作流委托属性（存量代码零改动） =======================
    @property
    def _active(self) -> WorkflowState:
        return self._workflows[self.active_workflow_id]

    @property
    def nodes(self) -> Dict[str, "WorkflowNode"]:
        return self._active.nodes

    @nodes.setter
    def nodes(self, value: Dict[str, "WorkflowNode"]) -> None:
        self._active.nodes = value

    @property
    def edges(self) -> List["NeuralEdge"]:
        return self._active.edges

    @edges.setter
    def edges(self, value: List["NeuralEdge"]) -> None:
        self._active.edges = value

    @property
    def shared_memory_bus(self) -> Dict[str, Any]:
        return self._active.shared_memory_bus

    @shared_memory_bus.setter
    def shared_memory_bus(self, value: Dict[str, Any]) -> None:
        self._active.shared_memory_bus = value

    @property
    def node_outputs(self) -> Dict[str, Any]:
        return self._active.node_outputs

    @node_outputs.setter
    def node_outputs(self, value: Dict[str, Any]) -> None:
        self._active.node_outputs = value

    @property
    def run_history(self) -> deque:
        return self._active.run_history

    @run_history.setter
    def run_history(self, value: deque) -> None:
        self._active.run_history = value

    @property
    def _recent_executions(self) -> deque:
        return self._active.recent_executions

    @_recent_executions.setter
    def _recent_executions(self, value: deque) -> None:
        self._active.recent_executions = value

    @property
    def selected_node_id(self) -> str:
        return self._active.selected_node_id

    @selected_node_id.setter
    def selected_node_id(self, value: str) -> None:
        self._active.selected_node_id = value

    @property
    def current_run_id(self) -> str:
        return self._active.current_run_id

    @current_run_id.setter
    def current_run_id(self, value: str) -> None:
        self._active.current_run_id = value

    @property
    def latest_sandbox_html(self) -> str:
        return self._active.latest_sandbox_html

    @latest_sandbox_html.setter
    def latest_sandbox_html(self, value: str) -> None:
        self._active.latest_sandbox_html = value

    @property
    def _round_seq(self) -> int:
        return self._active.round_seq

    @_round_seq.setter
    def _round_seq(self, value: int) -> None:
        self._active.round_seq = value

    @property
    def _cycle_layer_hit(self) -> bool:
        return self._active.cycle_layer_hit

    @_cycle_layer_hit.setter
    def _cycle_layer_hit(self, value: bool) -> None:
        self._active.cycle_layer_hit = value

    # ======================= T32：工作流切换 =======================
    def topology_has_cycle(self, nodes_data: List[Dict[str, Any]], edges_data: List[Dict[str, Any]]) -> bool:
        """T33：对任意外部拓扑数据做 Kahn 环检测（导入校验用，不触碰引擎状态）"""
        adj: Dict[str, List[str]] = defaultdict(list)
        indeg: Dict[str, int] = {str(n.get("id")): 0 for n in nodes_data}
        for e in edges_data:
            src, dst = str(e.get("source")), str(e.get("target"))
            if src in indeg and dst in indeg:
                adj[src].append(dst)
                indeg[dst] += 1
        queue = deque(k for k, v in indeg.items() if v == 0)
        seen = 0
        while queue:
            cur = queue.popleft()
            seen += 1
            for nxt in adj[cur]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
        return seen != len(indeg)

    async def reload_active_from_store(self) -> "WorkflowSnapshot":
        """T33：从存储重载激活工作流（导入到当前工作流后调用），并广播快照"""
        row = await self.checkpoint_store.get_workflow_row(self.active_workflow_id)
        if row is None:
            raise ValueError(f"工作流不存在: {self.active_workflow_id}")
        state = WorkflowState(current_run_id=f"run_{uuid.uuid4().hex[:6]}")
        if row["nodes"]:
            state.nodes = {n["id"]: WorkflowNode(**n) for n in row["nodes"]}
        if row["edges"]:
            state.edges = [NeuralEdge(**e) for e in row["edges"]]
        state.latest_sandbox_html = self._active.latest_sandbox_html
        self._workflows[self.active_workflow_id] = state
        snap = self.get_snapshot()
        await self.ws_manager.broadcast("workflow_snapshot", snap.model_dump())
        return snap

    async def switch_workflow(self, workflow_id: str) -> "WorkflowSnapshot":
        """切换激活工作流：先持久化当前，再载入目标（不存在则 404 语义由路由处理）"""
        if workflow_id == self.active_workflow_id:
            return self.get_snapshot()
        row = await self.checkpoint_store.get_workflow_row(workflow_id)
        if row is None and workflow_id == self.DEFAULT_WORKFLOW_ID:
            # T51 实证修复：persist=0 时 default 从不落库，切走后再切回会 404 卡死激活流——
            # 以当前内存 default 态播种工作流行（幂等）
            await self.checkpoint_store.save_workflow(
                workflow_id,
                workflow_id,
                [n.model_dump() for n in self.nodes.values()],
                [e.model_dump() for e in self.edges],
            )
            row = await self.checkpoint_store.get_workflow_row(workflow_id)
        if row is None:
            raise ValueError(f"工作流不存在: {workflow_id}")
        await self.save_topology()
        state = self._workflows.get(workflow_id)
        if state is None:
            state = WorkflowState(current_run_id=f"run_{uuid.uuid4().hex[:6]}")
            if row["nodes"]:
                state.nodes = {n["id"]: WorkflowNode(**n) for n in row["nodes"]}
            if row["edges"]:
                state.edges = [NeuralEdge(**e) for e in row["edges"]]
            state.latest_sandbox_html = self._default_sandbox_template(f"工作流 {row['name']}")
            self._workflows[workflow_id] = state
        self.active_workflow_id = workflow_id
        self.status = WorkflowStatus.RUNNING
        self._debug_mode = False
        self._pause_gate.set()
        await self.append_log(f"[Workflow] 已切换到工作流 {workflow_id}（{len(state.nodes)} 节点）")
        snap = self.get_snapshot()
        await self.ws_manager.broadcast("workflow_snapshot", snap.model_dump())
        return snap

    def _save_topology_sync(self) -> None:
        """T32：同步持久化激活工作流到 workflows 表（供 asyncio.to_thread 调度）"""
        with SQLITE_WRITE_LOCK:  # T21：写串行化
            with sqlite_connect(self.checkpoint_store.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO workflows (id, name, nodes_json, edges_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        nodes_json = excluded.nodes_json,
                        edges_json = excluded.edges_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        self.active_workflow_id,
                        self.active_workflow_id,
                        json.dumps([n.model_dump() for n in self.nodes.values()], ensure_ascii=False),
                        json.dumps([e.model_dump() for e in self.edges], ensure_ascii=False),
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()

    async def save_topology(self) -> None:
        """将当前节点与连线持久化到 SQLite（增删节点/连线、位置与配置变更、RESET 后调用）"""
        if not self.persist_topology:
            return
        try:
            await asyncio.to_thread(self._save_topology_sync)
        except Exception as exc:
            await self.append_log(f"[Warn] 拓扑持久化失败: {exc}")

    def _load_topology_sync(self) -> None:
        """T32：启动时同步还原激活工作流（workflows 表；旧 topology 表自动迁移为 default）"""
        try:
            with sqlite_connect(self.checkpoint_store.db_path) as conn:
                row = conn.execute(
                    "SELECT nodes_json, edges_json FROM workflows WHERE id = ?",
                    (self.active_workflow_id,),
                ).fetchone()
                if row is None:
                    # 旧库迁移：topology 单行表 → workflows.default
                    has_topology = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='topology'"
                    ).fetchone()
                    legacy = (
                        conn.execute("SELECT nodes_json, edges_json FROM topology WHERE id = 1").fetchone()
                        if has_topology
                        else None
                    )
                    if legacy is not None:
                        conn.execute(
                            """
                            INSERT INTO workflows (id, name, nodes_json, edges_json, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET nodes_json = excluded.nodes_json, edges_json = excluded.edges_json
                            """,
                            (
                                self.DEFAULT_WORKFLOW_ID,
                                "默认工作流",
                                legacy[0],
                                legacy[1],
                                datetime.now().isoformat(),
                            ),
                        )
                        conn.commit()
                        row = conn.execute(
                            "SELECT nodes_json, edges_json FROM workflows WHERE id = ?",
                            (self.active_workflow_id,),
                        ).fetchone()
                    else:
                        # 全新库：把当前内存默认拓扑作为 default 落库
                        conn.execute(
                            """
                            INSERT INTO workflows (id, name, nodes_json, edges_json, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET nodes_json = excluded.nodes_json, edges_json = excluded.edges_json
                            """,
                            (
                                self.active_workflow_id,
                                self.active_workflow_id,
                                json.dumps([n.model_dump() for n in self.nodes.values()], ensure_ascii=False),
                                json.dumps([e.model_dump() for e in self.edges], ensure_ascii=False),
                                datetime.now().isoformat(),
                            ),
                        )
                        conn.commit()
                        return
            nodes_data = json.loads(row[0])
            edges_data = json.loads(row[1])
            if nodes_data:
                self.nodes = {n["id"]: WorkflowNode(**n) for n in nodes_data}
            if edges_data:
                self.edges = [NeuralEdge(**e) for e in edges_data]
        except Exception as exc:
            # 还原失败（库损坏/契约变更）时保留默认拓扑，不阻断启动
            logger.warning(f"topology_restore_failed workflow_id={self.active_workflow_id} error={exc}")

    def _default_sandbox_template(self, title: str) -> str:
        ts = datetime.now().strftime("%H:%M:%S")
        return f"""<div class="p-4 bg-slate-900/95 text-slate-100 rounded-xl border border-cyan-500/40 shadow-lg font-sans">
  <div class="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
    <span class="text-xs font-bold text-cyan-400">⚡ DOM RENDERER LIVE SANDBOX</span>
    <span class="text-[10px] px-2 py-0.5 bg-emerald-500/20 text-emerald-300 rounded-full">Hydrated @ {ts}</span>
  </div>
  <h3 class="text-sm font-semibold text-white mb-2">{title}</h3>
  <div class="grid grid-cols-3 gap-2 text-center">
    <div class="p-2 rounded bg-slate-800/80 border border-slate-700">
      <div class="text-[10px] text-slate-400">突触延迟</div>
      <div class="text-sm font-bold text-emerald-400">8ms</div>
    </div>
    <div class="p-2 rounded bg-slate-800/80 border border-slate-700">
      <div class="text-[10px] text-slate-400">意图置信度</div>
      <div class="text-sm font-bold text-cyan-400">99.2%</div>
    </div>
    <div class="p-2 rounded bg-slate-800/80 border border-slate-700">
      <div class="text-[10px] text-slate-400">UI 生成率</div>
      <div class="text-sm font-bold text-purple-400">98.6%</div>
    </div>
  </div>
</div>"""

    def _init_components(self) -> List[ComponentItem]:
        return [
            ComponentItem(id="trig_events", category="触发器", category_en="Triggers", name="页面事件", name_en="Events", icon="Zap", theme_color="#10b981"),
            ComponentItem(id="trig_schedule", category="触发器", category_en="Triggers", name="定时触发", name_en="Schedule", icon="Clock", theme_color="#10b981"),
            ComponentItem(id="perc_nlu", category="感知解析", category_en="Perception", name="自然语言理解", name_en="NLU", icon="MessageSquare", theme_color="#38bdf8"),
            ComponentItem(id="perc_vision", category="感知解析", category_en="Perception", name="视觉输入", name_en="Vision", icon="Eye", theme_color="#38bdf8"),
            ComponentItem(id="agent_intent", category="AI 智能体", category_en="Agents", name="意图分析", name_en="Intent Agent", icon="Network", theme_color="#6366f1"),
            ComponentItem(id="agent_codegen", category="AI 智能体", category_en="Agents", name="代码生成", name_en="CodeGen", icon="Code", theme_color="#6366f1"),
            ComponentItem(id="logic_transform", category="数据逻辑", category_en="Logic", name="数据转换", name_en="Transform", icon="ArrowLeftRight", theme_color="#a855f7"),
            ComponentItem(id="llm_generic", category="AI 智能体", category_en="Agents", name="LLM 生成", name_en="LLM Generic", icon="Sparkles", theme_color="#6366f1"),
            ComponentItem(id="http_request", category="数据逻辑", category_en="Logic", name="HTTP 请求", name_en="HTTP Request", icon="Globe", theme_color="#a855f7"),
            ComponentItem(id="logic_state", category="数据逻辑", category_en="Logic", name="状态管理", name_en="State", icon="Database", theme_color="#a855f7"),
            ComponentItem(id="fe_assemble", category="前端渲染", category_en="Frontend", name="组件装配", name_en="Assemble", icon="LayoutGrid", theme_color="#38bdf8"),
            ComponentItem(id="fe_render", category="前端渲染", category_en="Frontend", name="DOM 渲染", name_en="Render", icon="Terminal", theme_color="#38bdf8"),
            ComponentItem(id="dep_test", category="部署", category_en="Deploy", name="沙盒测试", name_en="Test", icon="FlaskConical", theme_color="#ec4899"),
            ComponentItem(id="dep_publish", category="部署", category_en="Deploy", name="发布", name_en="Publish", icon="Rocket", theme_color="#ec4899"),
        ]

    def _init_nodes(self) -> Dict[str, WorkflowNode]:
        base_cfg = {
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
        items = [
            WorkflowNode(
                id="node_event_capturer",
                type="event_capturer",
                title="事件捕获",
                subtitle="(Event Capturer)",
                position=NodePosition(x=55, y=235),
                theme_color="#10b981",
                status="active",
                progress=100.0,
                confidence=99.2,
                latency_ms=8,
                config_json={**base_cfg, "stream_source": "DOM_Observer_v2"},
            ),
            WorkflowNode(
                id="node_intent_agent",
                type="intent_agent",
                title="意图识别智能体",
                subtitle="(Intent Agent)",
                position=NodePosition(x=305, y=235),
                theme_color="#6366f1",
                status="active",
                progress=100.0,
                confidence=99.2,
                latency_ms=8,
                config_json={**base_cfg, "model": "neural-intent-v2.8"},
            ),
            WorkflowNode(
                id="node_ui_gen",
                type="ui_generation",
                title="前端UI生成",
                subtitle="(UI Generation Agent)",
                position=NodePosition(x=610, y=95),
                theme_color="#38bdf8",
                status="active",
                progress=98.6,
                confidence=98.6,
                latency_ms=8,
                config_json=base_cfg,
            ),
            WorkflowNode(
                id="node_co_agent",
                type="co_agent",
                title="多Agent协作器",
                subtitle="(Co-Agent)",
                position=NodePosition(x=610, y=305),
                theme_color="#a855f7",
                status="active",
                progress=99.2,
                confidence=99.2,
                latency_ms=8,
                config_json={**base_cfg, "consensus_protocol": "Byzantine_Synapse"},
            ),
            WorkflowNode(
                id="node_dom_renderer",
                type="dom_renderer",
                title="页面渲染引擎",
                subtitle="(DOM Renderer)",
                position=NodePosition(x=610, y=435),
                theme_color="#3b82f6",
                status="success",
                progress=100.0,
                confidence=99.2,
                latency_ms=8,
                config_json={**base_cfg, "sandbox_isolation": "ShadowDOM_Strict"},
            ),
        ]
        return {n.id: n for n in items}

    def _init_edges(self) -> List[NeuralEdge]:
        return [
            NeuralEdge(id="edge_1_2", source="node_event_capturer", target="node_intent_agent", latency_ms=8, confidence_pct=99.2, connection_status="已连接", active_pulse=True),
            NeuralEdge(id="edge_2_3a", source="node_intent_agent", target="node_ui_gen", latency_ms=8, confidence_pct=99.2, connection_status="已连接", active_pulse=True),
            NeuralEdge(id="edge_2_3b", source="node_intent_agent", target="node_co_agent", latency_ms=8, confidence_pct=99.2, connection_status="已连接", active_pulse=True),
            NeuralEdge(id="edge_2_3c", source="node_intent_agent", target="node_dom_renderer", latency_ms=8, confidence_pct=99.2, connection_status="已连接", active_pulse=True),
        ]

    def compile_topological_layers(self) -> List[List[str]]:
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: Dict[str, List[str]] = defaultdict(list)

        for edge in self.edges:
            if edge.source in self.nodes and edge.target in self.nodes:
                adj[edge.source].append(edge.target)
                in_degree[edge.target] += 1

        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        layers: List[List[str]] = []
        visited_count = 0

        while queue:
            current_layer = list(queue)
            queue.clear()
            layers.append(current_layer)
            visited_count += len(current_layer)

            for u in current_layer:
                for v in adj[u]:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        queue.append(v)

        if visited_count < len(self.nodes):
            # Cyclic Agent Graph：环上节点作为反馈层兜底（Kahn 算法无法消化的剩余节点整体入反馈层）
            remaining = [nid for nid, deg in in_degree.items() if deg > 0]
            layers.append(remaining)
            self._cycle_layer_hit = True

        return layers

    def would_create_cycle(self, source: str, target: str) -> bool:
        """判断新增 source->target 连线是否会成环：从 target 沿现有边 DFS，能回到 source 即为真"""
        if source not in self.nodes or target not in self.nodes:
            return False
        seen: Set[str] = set()
        frontier = [target]
        while frontier:
            cur = frontier.pop()
            if cur == source:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            for e in self.edges:
                if e.source == cur:
                    frontier.append(e.target)
        return False

    def _failed_downstream(self, failed: Set[str]) -> Set[str]:
        """计算失败节点的全部传递下游（沿边 BFS 可达），用于单节点错误隔离的 skipped 标记"""
        reach: Set[str] = set()
        frontier = list(failed)
        while frontier:
            cur = frontier.pop()
            for e in self.edges:
                if e.source == cur and e.target in self.nodes and e.target not in reach:
                    reach.add(e.target)
                    frontier.append(e.target)
        return reach

    async def append_log(self, line: str) -> None:
        self.terminal_logs.append(line)
        if len(self.terminal_logs) > 60:
            self.terminal_logs = self.terminal_logs[-60:]
        await self.ws_manager.broadcast(
            "terminal_log",
            {"line": line, "logs": self.terminal_logs[-12:]},
        )

    async def _execute_single_node(self, node: WorkflowNode) -> None:
        await self._pause_gate.wait()
        if self._debug_mode:
            await self.append_log(f"[Debug] 断点捕获 -> {node.title}，等待下一步指令...")
            await self._debug_step_gate.wait()
            self._debug_step_gate.clear()

        t0 = time.perf_counter()
        api_key = self.llm_config.get("api_key", "")

        # 0. 收集上游节点最近输出作为本节点输入（数据真正沿连线流动）
        inputs: Dict[str, Any] = {
            e.source: self.node_outputs.get(e.source)
            for e in self.edges
            if e.target == node.id and e.source in self.nodes
        }

        # 1. 调用 12 算子注册表执行对应算子逻辑（type 先经别名表归一化，上游输出经 inputs 注入）
        op_result = await self.operator_registry.execute(
            operator_type=node.type,
            node_config=node.config_json,
            shared_bus=self.shared_memory_bus,
            inputs=inputs,
        )

        # 2. 若为前端 UI 生成或代码生成节点，驱动大模型或内置内核并经过 AST 自愈编译器
        if node.type in ("ui_generation", "agent_codegen"):
            raw_html = ""
            if api_key:
                # T24/T31：经 LLMClient 走信号量/可配超时 + SSE 流式（增量经 node_stream 推送）；
                # T12 的解析复检按尝试即时进行
                llm = LLMClient()

                async def _make_transport() -> httpx.AsyncBaseTransport:
                    allow_private_llm = os.getenv("AIGENT_ALLOW_PRIVATE_LLM", "") == "1"
                    pinned_url = await resolve_and_pin_api_base(
                        self.llm_config["api_base"], allow_private=allow_private_llm
                    )
                    return IPPinnedTransport(pinned_ip=httpx.URL(pinned_url).host)

                messages = [
                    {"role": "system", "content": "Generate a compact Tailwind HTML card snippet for a cyberpunk AI telemetry widget. Return pure HTML only."},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"config": node.config_json, "inputs": inputs},
                            ensure_ascii=False,
                        ),
                    },
                ]
                result_parts: List[str] = []
                stream_error: Optional[str] = None
                async for chunk in llm.chat_completion_stream(
                    api_base=self.llm_config["api_base"],
                    api_key=api_key,
                    model=self.llm_config["model"],
                    messages=messages,
                    max_tokens=1024,
                    transport_factory=_make_transport,
                ):
                    if chunk.get("delta"):
                        result_parts.append(chunk["delta"])
                        # T31 契约：增量事件 node_stream（node_id + delta）；最终态仍由 node_update 携带
                        await self.ws_manager.broadcast(
                            "node_stream", {"node_id": node.id, "delta": chunk["delta"]}
                        )
                    if chunk.get("done"):
                        stream_error = chunk.get("error")
                full_text = "".join(result_parts)
                if stream_error is None and full_text.strip():
                    raw_html = full_text
                    node.degraded = False
                    metrics.observe_llm("success")
                else:
                    # 不再静默吞掉：LLM 失败必须留痕后降级内置模板（degraded 徽章对前端可见）
                    node.degraded = True
                    metrics.observe_llm("failure")
                    metrics.observe_llm("degraded")
                    logger.warning(f"llm_stream_failed node_id={node.id} degraded=true error={stream_error}")
                    await self.append_log(f"[Warn] LLM 调用失败，降级内置模板: {stream_error}")
                    await asyncio.sleep(0.3)
                    raw_html = self._default_sandbox_template(
                        f"AI 生成组件 #{random.randint(100, 999)} ({node.config_json.get('name', 'Agent')})"
                    )
            else:
                await asyncio.sleep(random.uniform(0.28, 0.5))
                node.degraded = False
                raw_html = self._default_sandbox_template(
                    f"实时神经元视图 · 置信度 {node.confidence}%"
                )

            ast_report = FrontendASTValidator.validate_and_heal(raw_html)
            self.latest_sandbox_html = ast_report.healed_code
            self.shared_memory_bus["ast_validation"] = {
                "is_valid": ast_report.is_valid,
                "security_score": ast_report.security_score,
                "dom_depth": ast_report.dom_depth,
                "element_count": ast_report.element_count,
            }
        else:
            await asyncio.sleep(random.uniform(0.25, 0.45))

        # 3. 真实测量的执行耗时与算子返回指标（不再夹逼 6~14ms、不再按节点 id 硬编码）
        elapsed_ms = max(1, int((time.perf_counter() - t0) * 1000))
        node.latency_ms = elapsed_ms
        node.confidence = float(op_result.get("confidence", 99.2))
        node.progress = 100.0
        node.status = "success"
        node.last_error = None
        metrics.observe_node(node.type, "success", elapsed_ms)  # T23

        # 4. 输出写入节点输出表供下游消费；shared_memory_bus 保留向后兼容
        self.node_outputs[node.id] = op_result.get("output")

        self.shared_memory_bus[node.id] = {
            "title": node.title,
            "confidence": node.confidence,
            "latency_ms": node.latency_ms,
            "updated_at": datetime.now().isoformat(),
        }
        await self.checkpoint_store.save_checkpoint(
            run_id=self.current_run_id,
            node_id=node.id,
            state_payload=self.shared_memory_bus,
            generated_code=self.latest_sandbox_html,
            # 断点携带当下拓扑快照：时间旅行回滚时节点与连线可随断点还原
            topology={
                "nodes": [n.model_dump() for n in self.nodes.values()],
                "edges": [e.model_dump() for e in self.edges],
            },
            workflow_id=self.active_workflow_id,
        )

        await self.append_log(f"Agent initialized: {node.confidence}%...")
        await self.ws_manager.broadcast(
            "node_update",
            {
                "node": node.model_dump(),
                "sandbox_html": self.latest_sandbox_html,
                "shared_memory_bus": self.shared_memory_bus,
            },
        )

    def _compute_radar_metrics(self) -> RadarMetrics:
        """由最近 50 次节点执行统计与当前拓扑推导真实雷达指标（不再随机伪造）"""
        total = max(len(self.nodes), 1)
        if not self._recent_executions:
            return RadarMetrics()
        confs = [r["confidence"] for r in self._recent_executions]
        lats = [r["latency_ms"] for r in self._recent_executions]
        ok_count = sum(1 for r in self._recent_executions if r["status"] in ("success", "active"))
        max_layer_width = max((len(l) for l in self.compile_topological_layers()), default=1)

        accuracy = round(sum(confs) / len(confs), 1)
        responsiveness = round(max(0.0, min(100.0, 100.0 - (sum(lats) / len(lats)) / 20.0)), 1)
        stability = round(ok_count / len(self._recent_executions) * 100.0, 1)
        concurrency = round(max_layer_width / total * 100.0, 1)
        radar_perception = round(
            sum(1 for n in self.nodes.values() if n.status in ("success", "active")) / total * 100.0, 1
        )
        return RadarMetrics(
            radar_perception=radar_perception,
            responsiveness=responsiveness,
            accuracy=accuracy,
            concurrency=concurrency,
            stability=stability,
        )

    async def _run_dag_round(self) -> None:
        """执行一轮完整 DAG：编译分层、单节点错误隔离、运行记录归档与真实雷达统计"""
        round_t0 = time.perf_counter()
        layers = self.compile_topological_layers()
        self._round_seq += 1
        round_id = f"{self.current_run_id}_r{self._round_seq}"
        started_at = datetime.now().isoformat()

        # 环路兜底命中时每轮至多告警一次（标志由 compile_topological_layers 置位）
        if self._cycle_layer_hit:
            self._cycle_layer_hit = False
            await self.append_log(
                "[Warn] 检测到环路拓扑：环上节点作为反馈层兜底执行 (Cyclic Agent Graph)"
            )

        failed: Set[str] = set()
        node_records: List[Dict[str, Any]] = []
        blocked = self._failed_downstream(failed)  # 初始为空集

        for layer_nodes in layers:
            runnable: List[WorkflowNode] = []
            for nid in layer_nodes:
                if nid not in self.nodes:
                    continue
                node = self.nodes[nid]
                if nid in blocked:
                    # 上游失败：本节点标记 skipped 并跳过执行（单节点错误隔离）
                    node.status = "skipped"
                    node.progress = 0.0
                    metrics.observe_node(node.type, "skipped", node.latency_ms)  # T23
                    node_records.append(
                        {"id": nid, "status": "skipped", "latency_ms": node.latency_ms, "error": None}
                    )
                    self._recent_executions.append(
                        {"confidence": node.confidence, "latency_ms": node.latency_ms, "status": "skipped"}
                    )
                else:
                    runnable.append(node)

            if runnable:
                results = await asyncio.gather(
                    *(self._execute_single_node(n) for n in runnable),
                    return_exceptions=True,
                )
                for node, res in zip(runnable, results):
                    if isinstance(res, asyncio.CancelledError):
                        raise res
                    if isinstance(res, BaseException):
                        # 某节点抛异常：标记 error 并留痕，其他分支继续（整轮不中断）
                        node.status = "error"
                        node.last_error = str(res)
                        node.progress = 0.0
                        metrics.observe_node(node.type, "error", node.latency_ms)  # T23
                        failed.add(node.id)
                        node_records.append(
                            {"id": node.id, "status": "error", "latency_ms": node.latency_ms, "error": node.last_error}
                        )
                        self._recent_executions.append(
                            {"confidence": node.confidence, "latency_ms": node.latency_ms, "status": "error"}
                        )
                        await self.append_log(f"[Error] 节点 {node.title}: {res}")
                    else:
                        node_records.append(
                            {"id": node.id, "status": node.status, "latency_ms": node.latency_ms, "error": node.last_error}
                        )
                        self._recent_executions.append(
                            {"confidence": node.confidence, "latency_ms": node.latency_ms, "status": node.status}
                        )
                # 本层出现失败后，重新计算受阻塞的传递下游
                blocked = self._failed_downstream(failed)

        # 运行记录归档（GET /runs 数据源，最多保留 20 轮）
        run_record = {
            "round_id": round_id,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(),
            "nodes": node_records,
        }
        self.run_history.append(run_record)
        # T26：同时落库（重启不丢）；失败不阻断轮次
        try:
            await self.checkpoint_store.save_run(
                round_id=round_id,
                run_id=self.current_run_id,
                started_at=started_at,
                finished_at=run_record["finished_at"],
                status="completed",
                nodes=node_records,
            )
        except Exception as exc:
            await self.append_log(f"[Warn] 运行记录落库失败: {exc}")

        # 雷达图由真实统计推导
        self.radar_metrics = self._compute_radar_metrics()
        # T23/T27：真实轮耗时 → 指标直方图 + ECG 数据源
        round_ms = (time.perf_counter() - round_t0) * 1000
        metrics.observe_round(round_ms)
        self.last_round_latency_ms = round_ms
        await self.append_log("Success...")
        await self.append_log("[System] Deploying to Sandbox...")

    async def _dag_execution_loop(self) -> None:
        while True:
            try:
                await self._run_dag_round()
                self.last_tick_monotonic = time.monotonic()  # T20 心跳
                self.loop_failure_counts["dag"] = 0  # T25 成功即清零
                await asyncio.sleep(1.6)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.loop_failure_counts["dag"] += 1  # T25：异常不吞，计数上报
                logger.exception(f"dag_loop_error run_id={self.current_run_id} count={self.loop_failure_counts['dag']} error={exc}")
                await self.append_log(f"[Error] Topological Executor: {exc}")
                await asyncio.sleep(1.0)

    def _telemetry_sample(self) -> float:
        """T27：ECG 采样值 = 最近一轮 DAG 总耗时归一化（0~1，2s 顶格；无轮数据时为 0 平线）"""
        return min(1.0, self.last_round_latency_ms / 2000.0)

    async def _telemetry_loop(self) -> None:
        while True:
            try:
                self._phase += 0.45
                # 真实系统采样：psutil.cpu_percent 首次调用返回 0.0 属正常，不再用正弦波伪造
                cpu_val = psutil.cpu_percent(interval=None)
                mem_val = round(psutil.virtual_memory().percent, 1)

                self.cpu_history = (self.cpu_history + [cpu_val])[-16:]
                self.memory_history = (self.memory_history + [mem_val])[-16:]

                # T27：ECG 波形 = 真实指标（最近一轮 DAG 总耗时，归一化到 0~1，无轮时重复上一值）
                self.ecg_waveform = (self.ecg_waveform + [self._telemetry_sample()])[-20:]

                # 遥测瘦身：sandbox_html 与 shared_memory_bus 已由 node_update 携带，不再重复下发
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
                self.last_tick_monotonic = time.monotonic()  # T20 心跳
                self.loop_failure_counts["telemetry"] = 0  # T25 成功即清零
            except asyncio.CancelledError:
                break
            except Exception:
                self.loop_failure_counts["telemetry"] += 1  # T25：计数不吞
                await asyncio.sleep(0.5)

    def readiness(self) -> Dict[str, Any]:
        """T20/T25 就绪探针数据：SQLite 可写 + 两个循环 task 存活 + 最近心跳 < 5s + 无连续异常。
        不泄露内部细节（不含 db 路径、密钥、拓扑）。"""
        sqlite_ok = True
        try:
            with sqlite3.connect(self.checkpoint_store.db_path, timeout=2.0) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS _readyz_probe (k TEXT PRIMARY KEY)")
                conn.execute("DROP TABLE IF EXISTS _readyz_probe")
        except Exception:
            sqlite_ok = False

        now = time.monotonic()
        last_tick = self.last_tick_monotonic
        tick_age = round(now - last_tick, 3) if last_tick is not None else None
        dag_alive = bool(self._engine_task and not self._engine_task.done())
        telemetry_alive = bool(self._telemetry_task and not self._telemetry_task.done())
        tick_ok = tick_age is not None and tick_age < 5.0
        failures = dict(self.loop_failure_counts)
        loop_healthy = max(failures.values(), default=0) < 3  # T25：连续失败阈值

        ready = sqlite_ok and dag_alive and telemetry_alive and tick_ok and loop_healthy
        return {
            "status": "ready" if ready else "not_ready",
            "checks": {
                "sqlite_writable": sqlite_ok,
                "dag_loop_alive": dag_alive,
                "telemetry_loop_alive": telemetry_alive,
                "last_tick_age_s": tick_age,
                "loop_failure_counts": failures,
            },
        }

    def start(self) -> None:
        # T25：cancelling()>0 的任务即将死透，也要重建——否则快速 lifespan 回收后双循环全灭
        for name in ("dag", "telemetry"):
            task = self._engine_task if name == "dag" else self._telemetry_task
            if task is None or task.done() or task.cancelling() > 0:
                coro = self._dag_execution_loop() if name == "dag" else self._telemetry_loop()
                new_task = asyncio.create_task(coro)
                if name == "dag":
                    self._engine_task = new_task
                else:
                    self._telemetry_task = new_task

    async def stop(self) -> None:
        for t in (self._engine_task, self._telemetry_task):
            if t and not t.done():
                t.cancel()
        # T25：等待取消真正落地（跨 loop 安全的 done() 轮询；engine 为模块级单例，
        # start/stop 可能来自不同事件循环，不能用 gather 携带跨 loop Future）。
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if all(t is None or t.done() for t in (self._engine_task, self._telemetry_task)):
                break
            await asyncio.sleep(0.02)

    def get_snapshot(self) -> WorkflowSnapshot:
        return WorkflowSnapshot(
            version="v2.8",
            workflow_id=self.active_workflow_id,
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

    async def handle_control(self, action: ControlAction) -> WorkflowSnapshot:
        if action == ControlAction.RUN:
            self._debug_mode = False
            self._debug_step_gate.set()
            self._pause_gate.set()
            self.status = WorkflowStatus.RUNNING
            await self.append_log("[System] 神经元拓扑图恢复全速运行 (RUNNING)...")
        elif action == ControlAction.PAUSE:
            self._pause_gate.clear()
            self.status = WorkflowStatus.PAUSED
            await self.append_log("[System] 神经元突触信号已冻结 (PAUSED)...")
        elif action == ControlAction.DEBUG:
            self._pause_gate.set()
            self._debug_mode = True
            self._debug_step_gate.set()
            self.status = WorkflowStatus.DEBUG
            await self.append_log("[Debug] 单步突触脉冲已放行 (STEP_DEBUG)...")
        elif action == ControlAction.RESET:
            self._debug_mode = False
            self._pause_gate.set()
            # 回归：RESET 必须放行单步门，否则调试挂起后工作循环永久冻结
            self._debug_step_gate.set()
            self.current_run_id = f"run_{uuid.uuid4().hex[:6]}"
            self._round_seq = 0
            self.nodes = self._init_nodes()
            self.edges = self._init_edges()
            self.node_outputs.clear()
            self.status = WorkflowStatus.RUNNING
            await self.save_topology()
            await self.append_log("[System] 拓扑状态与沙盒已重置...")

        snap = self.get_snapshot()
        await self.ws_manager.broadcast("workflow_snapshot", snap.model_dump())
        return snap

    async def add_custom_node_from_sidebar(
        self, comp_id: str, x: float, y: float, connect_from: Optional[str] = None
    ) -> WorkflowNode:
        comp = next((c for c in self.components if c.id == comp_id), None)
        if not comp:
            raise ValueError(f"未知算子 ID: {comp_id}")

        new_id = f"node_{comp.id}_{uuid.uuid4().hex[:4]}"
        new_node = WorkflowNode(
            id=new_id,
            type=comp.id,
            title=comp.name,
            subtitle=f"({comp.name_en})",
            position=NodePosition(x=x, y=y),
            theme_color=comp.theme_color,
            status="active",
            progress=100.0,
            confidence=99.2,
            latency_ms=8,
            config_json={
                "name": f"{comp.name_en}.agent",
                "anenet5": {"enalen": "Pna", "data": {"name": comp.name, "type": "准确度", "temndary": comp.category_en}},
            },
        )
        self.nodes[new_id] = new_node
        # 连接策略：显式 connect_from 优先；否则默认挂到意图识别智能体（保持原行为）；均不可用则不建边
        link_source: Optional[str] = None
        if connect_from and connect_from in self.nodes:
            link_source = connect_from
        elif "node_intent_agent" in self.nodes:
            link_source = "node_intent_agent"
        if link_source:
            self.edges.append(
                NeuralEdge(
                    id=f"edge_auto_{uuid.uuid4().hex[:4]}",
                    source=link_source,
                    target=new_id,
                    latency_ms=8,
                    confidence_pct=99.2,
                    connection_status="已连接",
                    active_pulse=True,
                )
            )
        await self.append_log(f"[Topology] 新增神经元算子: {comp.name}，已动态重编译 DAG")
        await self.ws_manager.broadcast("workflow_snapshot", self.get_snapshot().model_dump())
        await self.save_topology()
        return new_node

    async def delete_node(self, node_id: str) -> None:
        """删除节点及其全部关联连线（级联），供 REST DELETE 路由调用"""
        if node_id not in self.nodes:
            raise KeyError(node_id)
        title = self.nodes[node_id].title
        del self.nodes[node_id]
        self.edges = [e for e in self.edges if e.source != node_id and e.target != node_id]
        self.node_outputs.pop(node_id, None)
        if self.selected_node_id == node_id:
            self.selected_node_id = next(iter(self.nodes), "")
        await self.append_log(f"[Topology] 已删除神经元节点: {title} ({node_id})，关联连线级联移除")
        await self.ws_manager.broadcast("workflow_snapshot", self.get_snapshot().model_dump())
        await self.save_topology()
