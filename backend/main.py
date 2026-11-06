# backend/main.py
# DEPRECATED: v1 旧入口，仅保留兼容；现役入口见 perfect_main.py。
from contextlib import asynccontextmanager
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from engine import ConnectionManager, NeuralWorkflowEngine
from models import ComponentItem, ControlRequest, WorkflowNode, WorkflowSnapshot

ws_manager = ConnectionManager()
workflow_engine = NeuralWorkflowEngine(ws_manager=ws_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时自动拉起神经元 DAG 引擎与 500ms 遥测流
    workflow_engine.start_background_tasks()
    yield
    await workflow_engine.stop_background_tasks()


app = FastAPI(
    title="前端智能体工作流平台后端 (AIGENT-WORKFLOW STUDIO v2.8)",
    version="2.8.0",
    lifespan=lifespan,
)

# 允许前端跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/components", response_model=List[ComponentItem])
async def get_component_library(q: str = Query(default="", description="左侧组件库搜索关键词")):
    """获取左侧 6 大分组算子组件库，支持按中英文名称实时搜索过滤"""
    if not q.strip():
        return workflow_engine.components
    keyword = q.strip().lower()
    return [
        comp
        for comp in workflow_engine.components
        if keyword in comp.name.lower()
        or keyword in comp.name_en.lower()
        or keyword in comp.category.lower()
    ]


@app.get("/api/v1/workflow", response_model=WorkflowSnapshot)
async def get_workflow_snapshot():
    """获取当前工作台全量状态快照（节点、神经突触连线、雷达图、JSON配置、终端日志）"""
    return workflow_engine.get_snapshot()


@app.post("/api/v1/workflow/control", response_model=WorkflowSnapshot)
async def control_workflow(req: ControlRequest):
    """处理顶部导航栏【运行 Run】、【暂停 Pause】、【调试 Debug】按钮动作"""
    return await workflow_engine.handle_control(req.action)


@app.put("/api/v1/workflow/nodes/{node_id}/config", response_model=WorkflowNode)
async def update_node_json_config(node_id: str, config_payload: Dict[str, Any]):
    """保存右侧【JSON 配置区】对指定智能体节点的实时修改"""
    try:
        return await workflow_engine.update_node_config(node_id, config_payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/search")
async def global_search(q: str = Query(..., min_length=1, description="顶部全局搜索框关键词")):
    """对应右上角【全局搜索】框，同时检索画布节点、左侧算子库与终端日志"""
    kw = q.strip().lower()
    matched_nodes = [
        n.model_dump()
        for n in workflow_engine.nodes.values()
        if kw in n.title.lower() or kw in n.subtitle.lower() or kw in n.id.lower()
    ]
    matched_components = [
        c.model_dump()
        for c in workflow_engine.components
        if kw in c.name.lower() or kw in c.name_en.lower()
    ]
    matched_logs = [line for line in workflow_engine.terminal_logs if kw in line.lower()]
    return {
        "query": q,
        "nodes": matched_nodes,
        "components": matched_components,
        "logs": matched_logs,
    }


@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """实时推送 CPU/内存波形、心电脉冲、节点进度及 AI 终端日志的 WebSocket 端点"""
    await ws_manager.connect(websocket)
    try:
        # 初次连接立即下发一次完整工作台快照
        initial_snapshot = workflow_engine.get_snapshot()
        await websocket.send_json(
            {"event": "workflow_snapshot", "data": initial_snapshot.model_dump()}
        )
        while True:
            # 接收前端发来的交互指令（如点击切换选中节点或发送控制命令）
            client_msg = await websocket.receive_json()
            msg_type = client_msg.get("type")
            if msg_type == "select_node":
                node_id = client_msg.get("node_id")
                if node_id in workflow_engine.nodes:
                    workflow_engine.selected_node_id = node_id
                    await websocket.send_json(
                        {
                            "event": "selected_node_changed",
                            "data": workflow_engine.nodes[node_id].model_dump(),
                        }
                    )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
