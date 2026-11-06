# backend/perfect_main.py
import asyncio
import hashlib
import hmac
import io
import ipaddress
import json
import os
import socket
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ast_validator import ASTValidationReport, FrontendASTValidator
from models import ComponentItem, ControlRequest, NeuralEdge, WorkflowNode, WorkflowSnapshot
from obs_logging import configure_logging, get_logger, request_id_var
from perfect_engine import ConnectionManager, PerfectNeuralEngine
from publisher import WorkflowArtifactPublisher

logger = get_logger("aigent.api")

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


AST_CODE_MAX_BYTES = 512 * 1024  # T13：/ast/validate code 上限 512KB
CONFIG_JSON_MAX_BYTES = 64 * 1024  # T13：节点 config_json 上限 64KB


class LLMConfigRequest(BaseModel):
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()  # T22：结构化 JSON 日志（幂等）
    logger.info(f"service_start version={app.version}")
    engine.start()
    yield
    logger.info("service_stop")
    await engine.stop()


app = FastAPI(
    title="AIGENT-WORKFLOW STUDIO v2.8 Complete Industrial Backend",
    version="2.8.0-ultimate",
    lifespan=lifespan,
)

# ======================= T10 全局鉴权（P1 安全加固） =======================
# 规则（生产化执行方案 T10）：
#   - 配置 AIGENT_ADMIN_TOKEN 后：所有非 GET/HEAD 路由、/publish/*、/settings/* 必须携带
#     X-Admin-Token（hmac.compare_digest 恒时比较）；
#   - 其余 GET 只读接口是否免令牌由 AIGENT_PUBLIC_READ=1 决定（默认不放行，同样需要令牌）；
#   - 未配置令牌 + 非回环来源 → 403（fail-closed，防止误暴露到局域网/公网）；
#   - /publish/live-app 因 iframe 无法携带自定义请求头，改用短期签名 URL（HMAC-SHA256 + 过期时间）。
# 注册顺序：本中间件先于 CORS 注册 → CORS 保持最外层，401/403 响应也会带上 CORS 头，前端可读。
TRUSTED_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}  # testclient = Starlette 测试客户端标记
AUTH_EXEMPT_PATHS = {"/healthz", "/readyz"}  # T20：健康检查免鉴权（不泄露内部细节）


def _admin_token() -> str:
    return os.getenv("AIGENT_ADMIN_TOKEN", "").strip()


def _ws_allowed_origins() -> List[str]:
    """WS Origin 白名单：与 CORS_ORIGINS 同源同默认（T11）"""
    return [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
        ).split(",")
        if o.strip()
    ]


def _authenticate_websocket(websocket: WebSocket) -> Optional[int]:
    """WS 握手鉴权：返回 None=通过；否则返回应使用的 close code。
    - Origin 校验独立于令牌：浏览器跨站 WS 攻击必带 Origin，非浏览器客户端（无 Origin）放行；
    - 令牌校验仅在配置 AIGENT_ADMIN_TOKEN 后启用：?token= 或 Sec-WebSocket-Protocol 子协议。"""
    origin = websocket.headers.get("origin", "")
    if origin and origin not in _ws_allowed_origins():
        return 4403
    token = _admin_token()
    if not token:
        return None
    supplied = websocket.query_params.get("token", "")
    if not supplied:
        for sub in websocket.scope.get("subprotocols") or []:
            sub_text = sub.decode("latin-1") if isinstance(sub, bytes) else str(sub)
            if sub_text == token:
                supplied = token
                break
    if supplied and hmac.compare_digest(supplied, token):
        return None
    return 4401


def _sign_live_app(exp_epoch: int, token: str) -> str:
    return hmac.new(token.encode("utf-8"), f"live-app:{exp_epoch}".encode("utf-8"), hashlib.sha256).hexdigest()


def _verify_live_app_signature(exp: str, sig: str, token: str) -> bool:
    try:
        exp_epoch = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_epoch < int(time.time()):
        return False
    return hmac.compare_digest(sig, _sign_live_app(exp_epoch, token))


class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in AUTH_EXEMPT_PATHS or request.method.upper() == "OPTIONS":
            return await call_next(request)

        token = _admin_token()
        client = request.client
        is_local = bool(client and client.host in TRUSTED_LOCAL_HOSTS)
        method = request.method.upper()

        if not token:
            if not is_local:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "服务未配置 AIGENT_ADMIN_TOKEN，仅允许本机回环访问"},
                )
            return await call_next(request)

        sensitive = path.startswith("/api/v1/publish/") or path.startswith("/api/v1/settings/")
        needs_token = method not in ("GET", "HEAD") or sensitive
        if not needs_token and os.getenv("AIGENT_PUBLIC_READ", "") != "1":
            needs_token = True  # 未显式开公共读时，GET 同样需要令牌

        if needs_token:
            supplied = request.headers.get("X-Admin-Token", "")
            ok = bool(supplied) and hmac.compare_digest(supplied, token)
            if not ok and path == "/api/v1/publish/live-app":
                # iframe 场景：短期签名 URL 兜底（exp + HMAC 签名）
                ok = _verify_live_app_signature(
                    request.query_params.get("exp", ""), request.query_params.get("sig", ""), token
                )
            if not ok:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "缺少或错误的管理令牌 (X-Admin-Token)"},
                    headers={"WWW-Authenticate": "X-Admin-Token"},
                )
        return await call_next(request)


app.add_middleware(AdminAuthMiddleware)


# ======================= T14 安全响应头（P1 安全加固） =======================
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """统一安全响应头。注册在 CORS 内侧、限流外侧之外→ 见文件末尾注册顺序：本中间件
    位于 CORS 之下（最外业务层），保证 401/429 等所有响应都带安全头。
    live-app 例外：不设 X-Frame-Options（该页面本就设计为可被 iframe 嵌入，由 CSP sandbox 控制）。"""

    XFO_EXEMPT_PATHS = {"/api/v1/publish/live-app"}

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path not in self.XFO_EXEMPT_PATHS:
            response.headers.setdefault("X-Frame-Options", "DENY")
        return response


# ======================= T13 限流与体积限制（P1 安全加固） =======================
class TokenBucketLimiter:
    """内存令牌桶（按 key 维度限流）。asyncio 单线程内 read-modify-write 无 await，天然原子。"""

    def __init__(self, rate_per_min: int, capacity: Optional[int] = None):
        self.rate_per_min = rate_per_min
        self.capacity = capacity if capacity is not None else max(1, rate_per_min)
        self._buckets: Dict[str, tuple] = {}  # key -> (tokens, last_monotonic)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (float(self.capacity), now))
        tokens = min(float(self.capacity), tokens + (now - last) * (self.rate_per_min / 60.0))
        if tokens < 1.0:
            self._buckets[key] = (tokens, now)
            return False
        self._buckets[key] = (tokens - 1.0, now)
        return True


WRITE_RATE_LIMIT_PER_MIN = int(os.getenv("AIGENT_RATE_LIMIT_PER_MIN", "60"))
STRICT_RATE_LIMIT_PER_MIN = int(os.getenv("AIGENT_STRICT_RATE_LIMIT_PER_MIN", "10"))
STRICT_RATE_PREFIXES = ("/api/v1/settings", "/api/v1/ast/validate", "/api/v1/publish/export-zip")
write_limiter = TokenBucketLimiter(WRITE_RATE_LIMIT_PER_MIN)
strict_limiter = TokenBucketLimiter(STRICT_RATE_LIMIT_PER_MIN)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """写接口 60/min/IP（严格面 10/min/IP）：/settings、/ast/validate、export-zip。

    注册在鉴权内侧、CORS 外侧：限流在令牌校验之前计数，天然抵御刷接口耗尽。
    """

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path
        if method in ("GET", "HEAD", "OPTIONS") or path in AUTH_EXEMPT_PATHS or not path.startswith("/api/"):
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        limiter = (
            strict_limiter
            if any(path.startswith(p) for p in STRICT_RATE_PREFIXES)
            else write_limiter
        )
        if not limiter.allow(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)

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
# T14 安全头中间件注册在最后 → 位于 CORS 之下最外层，401/429 等全部响应都带安全头
app.add_middleware(SecurityHeadersMiddleware)


# ======================= T22 请求日志与 X-Request-ID（P2 可观测） =======================
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """每请求生成 X-Request-ID：写回响应头并注入结构化日志（request_id 经 contextvar 传播）"""

    async def dispatch(self, request: Request, call_next):
        rid = uuid.uuid4().hex[:12]
        ctx_token = request_id_var.set(rid)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(f"http_request {request.method} {request.url.path} rid={rid} error")
            request_id_var.reset(ctx_token)
            raise
        duration_ms = (time.perf_counter() - t0) * 1000
        response.headers["X-Request-ID"] = rid
        logger.info(f"http_request {request.method} {request.url.path} status={response.status_code} duration_ms={duration_ms:.1f} rid={rid}")
        request_id_var.reset(ctx_token)
        return response


app.add_middleware(RequestLoggingMiddleware)


@app.get("/healthz")
async def healthz():
    """T20：进程存活探针（免鉴权、无依赖检查，仅证明服务在）"""
    return {"status": "ok", "version": app.version}


@app.get("/readyz")
async def readyz():
    """T20/T25：就绪探针（免鉴权）：SQLite 可写 + 引擎双循环存活 + 心跳 < 5s + 无连续异常"""
    report = engine.readiness()
    if report["status"] != "ready":
        return JSONResponse(status_code=503, content=report)
    return report


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
    # T13：节点总数上限（默认 200，AIGENT_MAX_NODES 可调）
    if len(engine.nodes) >= int(os.getenv("AIGENT_MAX_NODES", "200")):
        raise HTTPException(status_code=413, detail="节点总数已达上限，请先删除部分节点")
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
    # T13：config_json 体积上限 64KB
    if len(json.dumps(config_json, ensure_ascii=False, default=str).encode("utf-8")) > CONFIG_JSON_MAX_BYTES:
        raise HTTPException(status_code=413, detail="config_json 超过 64KB 上限")
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
    # T13：连线总数上限（默认 500，AIGENT_MAX_EDGES 可调）
    if len(engine.edges) >= int(os.getenv("AIGENT_MAX_EDGES", "500")):
        raise HTTPException(status_code=413, detail="连线总数已达上限，请先删除部分连线")
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
    # T13：code 体积上限 512KB
    if len(req.code.encode("utf-8")) > AST_CODE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="code 超过 512KB 上限")
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

    T12 后实际防 rebinding 的位置在 perfect_engine.resolve_and_pin_api_base：每次真实 LLM
    请求前重新解析复检并按校验通过的 IP 直连（保留 Host/SNI），设置校验与本函数仅作前置快筛。
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


# T15：Tailwind Play 运行时脚本本地化（原 live-app 依赖 https://cdn.tailwindcss.com 外部 CDN）
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/v1/publish/live-app", response_class=HTMLResponse)
async def view_published_live_app(request: Request):
    # CSP sandbox（不带 allow-same-origin）使页面处于不透明源：即使有残留脚本也读不到 API 同源数据。
    # T15：脚本仅允许本地 vendor 的 Tailwind Play（按请求 host 生成绝对地址，规避 opaque origin 下
    # 'self' 失效问题），script-src 不再放行外部 CDN 与 'unsafe-inline'；
    # style-src 保留 'unsafe-inline'（净化产物为任意 LLM 输出的内联样式，hash 无法静态枚举）。
    base = str(request.base_url).rstrip("/")
    sandbox_csp = (
        "sandbox allow-scripts; default-src 'none'; "
        f"script-src {base}/static/vendor/tailwindcss-play.js; "
        "style-src 'unsafe-inline'; img-src data: https:"
    )
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>AIGENT-WORKFLOW Live App</title>
  <script src="{base}/static/vendor/tailwindcss-play.js"></script>
</head>
<body class="bg-[#070a12] text-slate-100 min-h-screen flex items-center justify-center p-6">
  <div class="w-full max-w-lg">{engine.latest_sandbox_html}</div>
</body>
</html>""",
        headers={"Content-Security-Policy": sandbox_csp},
    )


@app.get("/api/v1/publish/live-app-url")
async def mint_live_app_url(ttl_seconds: int = Query(default=300, ge=10, le=3600)):
    """为 iframe/浏览器直开场景签发 live-app 短期签名 URL（该页面无法携带 X-Admin-Token 头）。
    本路由自身受鉴权保护：仅持有令牌者可换取签名 URL。"""
    token = _admin_token()
    if not token:
        return {"url": "/api/v1/publish/live-app", "signed": False, "expires_at": None}
    exp = int(time.time()) + ttl_seconds
    return {
        "url": f"/api/v1/publish/live-app?exp={exp}&sig={_sign_live_app(exp, token)}",
        "signed": True,
        "expires_at": exp,
    }


@app.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    # T11：先完成握手再鉴权，失败以自定义关闭码断开（浏览器可在 onclose 中读到 4401/4403）
    await websocket.accept()
    close_code = _authenticate_websocket(websocket)
    if close_code is not None:
        await websocket.close(code=close_code)
        return
    await ws_manager.connect(websocket, accept=False)
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
