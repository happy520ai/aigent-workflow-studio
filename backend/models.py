# backend/models.py
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    IDLE = "已就绪"
    RUNNING = "运行中"
    PAUSED = "已暂停"
    DEBUG = "调试中"
    ERROR = "异常"


class ControlAction(str, Enum):
    RUN = "run"
    PAUSE = "pause"
    DEBUG = "debug"
    RESET = "reset"


class ControlRequest(BaseModel):
    action: ControlAction
    target_node_id: Optional[str] = None


class ComponentItem(BaseModel):
    id: str
    category: str
    category_en: str
    name: str
    name_en: str
    icon: str
    theme_color: str


class NodePosition(BaseModel):
    x: float
    y: float


class RadarMetrics(BaseModel):
    radar_perception: float = Field(default=92.0, description="感知维度")
    responsiveness: float = Field(default=96.5, description="响应度")
    accuracy: float = Field(default=99.2, description="准确度")
    concurrency: float = Field(default=88.0, description="并发协同度")
    stability: float = Field(default=95.4, description="渲染稳定度")


class WorkflowNode(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str
    position: NodePosition
    theme_color: str
    status: str = "idle"  # idle | active | success | error | skipped
    progress: float = 0.0
    confidence: float = 99.2
    latency_ms: int = 8
    config_json: Dict[str, Any]
    last_error: Optional[str] = None  # 单节点错误隔离：最近一次执行失败的异常信息
    degraded: bool = False  # T24：LLM 调用降级（用内置模板兜底）时置位，前端显示徽章


class NeuralEdge(BaseModel):
    id: str
    source: str
    target: str
    latency_ms: int = 8
    confidence_pct: float = 99.2
    connection_status: str = "已连接"
    active_pulse: bool = False


class SystemTelemetry(BaseModel):
    cpu_history: List[float]
    memory_history: List[float]
    ecg_waveform: List[float]
    radar_metrics: RadarMetrics


class WorkflowSnapshot(BaseModel):
    version: str = "v2.8"
    project_status: WorkflowStatus
    selected_node_id: str
    nodes: List[WorkflowNode]
    edges: List[NeuralEdge]
    telemetry: SystemTelemetry
    terminal_logs: List[str]
