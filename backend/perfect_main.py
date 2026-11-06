# backend/perfect_main.py
import asyncio
import hmac
import io
import ipaddress
import os
import socket
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ast_validator import ASTValidationReport, FrontendASTValidator
from models import ComponentItem, ControlRequest, NeuralEdge, WorkflowNode, WorkflowSnapshot
from perfect_engine import ConnectionManager, PerfectNeuralEngine
from publisher import WorkflowArtifactPublisher

ws_manager = ConnectionManager()
engine = PerfectNeuralEngine(
    ws_manager=ws_manager,
    persist_topology=os.getenv("AIGENT_PERSIST_TOPOLOGY", "1") == "1",
)


class AddNodeRequest(BaseModel):
    component_id: str
    x: float = 460.0
    y: float = 520.0
    connect_from: Optional[str] = None  # 可选：新节点接入的父节点 id


class MoveNodeRequest(BaseModel):
    x: float
    y: float


class CreateEdgeRequest(BaseModel):
    source: str
    target: str


class ASTValidateRequest(BaseModel):
    code: str


class LLMConfigRequest(BaseModel):
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.start()
    yield
    await engine.stop()


app = FastAPI(
    title="AIGENT-WORKFLOW STUDIO v2.8 Complete Industrial Backend",
    version="2.8.0-ultimate",
    lifespan=lifespan,
)

# CORS 白名单：环境变量 CORS_ORIGINS（逗号分隔），默认仅放行本地开发端口。
# 注意 allow_credentials=False 不得与通配符 "*" 同用。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
        ).split(",")
        if o.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/components", response_model=List[ComponentItem])
async def list_components(q: str = Query(default="")):
    if not q.strip():
        return engine.components
    kw = q.strip().lower()
    return [c for c in engine.components if kw in c.name.lower() or kw in c.name_en.lower()]


@app.get("/api/v1/workflow", response_model=WorkflowSnapshot)
async def get_workflow():
    return engine.get_snapshot()


@app.post("/api/v1/workflow/control", response_model=WorkflowSnapshot)
async def control_workflow(req: ControlRequest):
    return await engine.handle_control(req.action)


@app.post("/api/v1/workflow/nodes", response_model=WorkflowNode)
async def create_node_from_sidebar(req: AddNodeRequest):
    try:
        return await engine.add_custom_node_from_sidebar(req.component_id, req.x, req.y, req.connect_from)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/workflow/nodes/{node_id}")
async def delete_workflow_node(node_id: str):
    if node_id not in engine.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    await engine.delete_node(node_id)
    return {"deleted": node_id}


@app.patch("/api/v1/workflow/nodes/{node_id}/position", response_model=WorkflowNode)
async def update_node_position(node_id: str, req: MoveNodeRequest):
    if node_id not in engine.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = engine.nodes[node_id]
    node.position.x = req.x
    node.position.y = req.y
    await engine.save_topology()
    await ws_manager.broadcast("workflow_snapshot", engine.get_snapshot().model_dump())
    return node


@app.put("/api/v1/workflow/nodes/{node_id}/config", response_model=WorkflowNode)
async def update_node_config(node_id: str, config_json: Dict[str, Any]):
    if node_id not in engine.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = engine.nodes[node_id]
    node.config_json = config_json
    engine.selected_node_id = node_id
    await engine.save_topology()
    await engine.append_log(f"[Inspector] 已热更新节点 {node.title} 的 JSON 配置")
    await ws_manager.broadcast("workflow_snapshot", engine.get_snapshot().model_dump())
    return node


@app.post("/api/v1/workflow/edges", response_model=NeuralEdge)
async def create_neural_edge(req: CreateEdgeRequest):
    if req.source not in engine.nodes or req.target not in engine.nodes:
        raise HTTPException(status_code=404, detail="源节点或目标节点不存在")
    if req.source == req.target:
        raise HTTPException(status_code=400, detail="不允许自环")
    if any(e.source == req.source and e.target == req.target for e in engine.edges):
        raise HTTPException(status_code=409, detail="连线已存在")
    if engine.would_create_cycle(req.source, req.target):
        raise HTTPException(status_code=409, detail="会形成环路")
    new_edge = NeuralEdge(
        id=f"edge_{uuid.uuid4().hex[:6]}",
        source=req.source,
        target=req.target,
        latency_ms=8,
        confidence_pct=99.2,
        connection_status="已连接",
        active_pulse=True,
    )
    engine.edges.append(new_edge)
    await engine.save_topology()
    await engine.append_log(
        f"[Synapse] 已建立突触连接: {engine.nodes[req.source].title} -> {engine.nodes[req.target].title}"
    )
    await ws_manager.broadcast("workflow_snapshot", engine.get_snapshot().model_dump())
    return new_edge


@app.get("/api/v1/runs")
async def list_run_history(limit: int = Query(default=20, ge=1, le=50)):
    """最近 DAG 运行记录（倒序）"""
    return list(reversed(engine.run_history))[:limit]


@app.get("/api/v1/search")
async def global_search(q: str = Query(..., min_length=1, description="顶部全局搜索框关键词")):
    """对应右上角【全局搜索】框，同时检索画布节点、左侧算子库与终端日志（结构同 v1）"""
    kw = q.strip().lower()
    matched_nodes = [
        n.model_dump()
        for n in engine.nodes.values()
        if kw in n.title.lower() or kw in n.subtitle.lower() or kw in n.id.lower()
    ]
    matched_components = [
        c.model_dump()
        for c in engine.components
        if kw in c.name.lower() or kw in c.name_en.lower()
    ]
    matched_logs = [line for line in engine.terminal_logs if kw in line.lower()]
    return {
        "query": q,
        "nodes": matched_nodes,
        "components": matched_components,
        "logs": matched_logs,
    }


@app.delete("/api/v1/workflow/edges/{edge_id}")
async def delete_neural_edge(edge_id: str):
    before_count = len(engine.edges)
    engine.edges = [e for e in engine.edges if e.id != edge_id]
    if len(engine.edges) == before_count:
        raise HTTPException(status_code=404, detail="突触连线不存在")
    await engine.save_topology()
    await engine.append_log(f"[Synapse] 已断开突触连接: {edge_id}")
    await ws_manager.broadcast("workflow_snapshot", engine.get_snapshot().model_dump())
    return {"deleted": edge_id}


@app.post("/api/v1/ast/validate", response_model=ASTValidationReport)
async def validate_ui_ast(req: ASTValidateRequest):
    report = FrontendASTValidator.validate_and_heal(req.code)
    engine.latest_sandbox_html = report.healed_code
    await engine.append_log(
        f"[AST-Validator] DOM深度:{report.dom_depth} | 节点数:{report.element_count} | 安全分:{report.security_score}%"
    )
    return report


@app.get("/api/v1/checkpoints")
async def get_time_travel_checkpoints(limit: int = 15):
    return await engine.checkpoint_store.list_checkpoints(limit=limit)


@app.post("/api/v1/checkpoints/{checkpoint_id}/restore")
async def restore_time_travel_checkpoint(checkpoint_id: str):
    # 改用按 id 精确取回，修掉原先只在最近 100 条里找的缺陷
    target = await engine.checkpoint_store.get_checkpoint(checkpoint_id)
    if not target:
        raise HTTPException(status_code=404, detail="未找到对应的断点快照")

    engine.shared_memory_bus = target["state_payload"]
    engine.latest_sandbox_html = target["generated_code"]
    engine.selected_node_id = target["node_id"]
    # 断点携带拓扑时一并还原节点与连线
    if target.get("topology_json"):
        topo = target["topology_json"]
        try:
            nodes_data = topo.get("nodes") or []
            edges_data = topo.get("edges") or []
            if nodes_data:
                engine.nodes = {n["id"]: WorkflowNode(**n) for n in nodes_data}
            if edges_data:
                engine.edges = [NeuralEdge(**e) for e in edges_data]
        except Exception as exc:
            await engine.append_log(f"[Warn] 断点拓扑还原失败，仅回滚状态: {exc}")
    await engine.append_log(f"[Time-Travel] 已回滚至历史断点 {checkpoint_id} ({target['timestamp']})")
    await ws_manager.broadcast("workflow_snapshot", engine.get_snapshot().model_dump())
    return {"status": "restored", "checkpoint": target}


@app.get("/api/v1/sandbox/preview")
async def get_live_sandbox_html():
    return {
        "html": engine.latest_sandbox_html,
        "memory_bus": engine.shared_memory_bus,
        "topological_layers": engine.compile_topological_layers(),
    }


async def require_admin(request: Request) -> None:
    """LLM 设置接口守卫：配置了管理令牌则校验令牌；未配置则仅允许本机回环访问"""
    admin_token = os.getenv("AIGENT_ADMIN_TOKEN", "").strip()
    if admin_token:
        supplied = request.headers.get("X-Admin-Token", "")
        if not hmac.compare_digest(supplied, admin_token):
            raise HTTPException(status_code=401, detail="缺少或错误的管理令牌 (X-Admin-Token)")
        return
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="仅允许本机访问；请设置 AIGENT_ADMIN_TOKEN 后携带 X-Admin-Token")


def validate_llm_api_base(url: str) -> str:
    """SSRF 校验：仅 http/https + 有主机名；可选主机白名单；默认拒绝解析到内网/保留地址的 api_base。

    注意：DNS 解析与实际请求之间存在时间差，无法完全防 DNS rebinding。
    """
    parsed_url = url.strip()
    if not (parsed_url.startswith("http://") or parsed_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="api_base 仅允许 http/https 协议")
    hostname = urlparse(parsed_url).hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="api_base 必须包含主机名")

    allowlist = [h.strip().lower() for h in os.getenv("LLM_API_BASE_ALLOWLIST", "").split(",") if h.strip()]
    if allowlist:
        if hostname.lower() not in allowlist:
            raise HTTPException(status_code=400, detail=f"api_base 主机不在白名单内: {hostname}")
        return parsed_url

    # 未配置白名单时逐地址解析校验（AIGENT_ALLOW_PRIVATE_LLM=1 可显式放行内网）
    if os.getenv("AIGENT_ALLOW_PRIVATE_LLM", "") != "1":
        try:
            addr_infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise HTTPException(status_code=400, detail=f"api_base 主机无法解析: {hostname}") from exc
        for info in addr_infos:
            ip_text = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_text)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                raise HTTPException(status_code=400, detail=f"api_base 指向内网/保留地址，已拒绝: {ip_text}")
    return parsed_url


async def validate_llm_api_base_async(url: str) -> str:
    """DNS 解析走线程池，避免阻塞事件循环；其余为纯 CPU 判断直接复用同步实现"""
    parsed_url = url.strip()
    if not (parsed_url.startswith("http://") or parsed_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="api_base 仅允许 http/https 协议")
    hostname = urlparse(parsed_url).hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="api_base 必须包含主机名")

    allowlist = [h.strip().lower() for h in os.getenv("LLM_API_BASE_ALLOWLIST", "").split(",") if h.strip()]
    if allowlist:
        if hostname.lower() not in allowlist:
            raise HTTPException(status_code=400, detail=f"api_base 主机不在白名单内: {hostname}")
        return parsed_url
    if os.getenv("AIGENT_ALLOW_PRIVATE_LLM", "") == "1":
        return parsed_url

    try:
        addr_infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail=f"api_base 主机无法解析: {hostname}") from exc
    for info in addr_infos:
        ip_text = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(status_code=400, detail=f"api_base 指向内网/保留地址，已拒绝: {ip_text}")
    return parsed_url


@app.get("/api/v1/settings/llm")
async def get_llm_settings(_: None = Depends(require_admin)):
    """读取当前大模型配置；绝不回显 api_key 原文，仅暴露末 4 位提示"""
    cfg = engine.llm_config
    api_key = cfg.get("api_key", "")
    return {
        "api_base": cfg.get("api_base", ""),
        "model": cfg.get("model", ""),
        "has_key": bool(api_key),
        "key_hint": f"sk-****{api_key[-4:]}" if api_key else "",
    }


@app.put("/api/v1/settings/llm")
async def update_llm_settings(req: LLMConfigRequest, _: None = Depends(require_admin)):
    validated_base = await validate_llm_api_base_async(req.api_base)
    engine.llm_config = {
        "api_key": req.api_key.strip(),
        "api_base": validated_base.rstrip("/"),
        "model": req.model.strip(),
    }
    await engine.append_log(f"[Settings] 已更新智能体大模型驱动内核: {req.model}")
    # 响应绝不回显 api_key
    return {"status": "updated", "model": req.model}


@app.get("/api/v1/publish/export-zip")
async def export_workflow_bundle_zip():
    zip_bytes = WorkflowArtifactPublisher.build_project_zip(
        sandbox_html=engine.latest_sandbox_html,
        workflow_snapshot=engine.get_snapshot().model_dump(),
        shared_memory_bus=engine.shared_memory_bus,
    )
    await engine.append_log("[Publish] 已打包并导出独立前端工程源码包 (aigent-bundle-v2.8.zip)")
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="aigent-bundle-v2.8.zip"'},
    )


@app.get("/api/v1/publish/live-app", response_class=HTMLResponse)
async def view_published_live_app():
    # CSP sandbox（不带 allow-same-origin）使页面处于不透明源：即使有残留脚本也读不到 API 同源数据
    sandbox_csp = (
        "sandbox allow-scripts; default-src 'none'; "
        "script-src https://cdn.tailwindcss.com 'unsafe-inline'; "
        "style-src 'unsafe-inline' https://cdn.tailwindcss.com; img-src data: https:"
    )
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>AIGENT-WORKFLOW Live App</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-[#070a12] text-slate-100 min-h-screen flex items-center justify-center p-6">
  <div class="w-full max-w-lg">{engine.latest_sandbox_html}</div>
</body>
</html>""",
        headers={"Content-Security-Policy": sandbox_csp},
    )


@app.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json(
            {
                "event": "workflow_snapshot",
                "data": engine.get_snapshot().model_dump(),
                "sandbox_html": engine.latest_sandbox_html,
            }
        )
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "select_node":
                nid = msg.get("node_id")
                if nid in engine.nodes:
                    engine.selected_node_id = nid
                    await websocket.send_json({"event": "selected_node_changed", "data": engine.nodes[nid].model_dump()})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
