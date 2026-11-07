# AIGENT-WORKFLOW STUDIO v3.0.0 · 后端服务

FastAPI 后端：**神经元 DAG 调度引擎 + 多工作流 + WebSocket 实时遥测 + 真实算子内核 + 安全/可观测层**。
技术栈：Python 3.11 + FastAPI 0.162 + Starlette 1.10 + Pydantic 2.14 + SQLite(WAL) + httpx + websockets。

## 目录结构

```text
backend/
├── perfect_main.py        # FastAPI 入口：路由全景 + 鉴权/限流/安全头/请求日志中间件 + 生产配置守卫
├── perfect_engine.py      # DAG 引擎：WorkflowState 多工作流、双循环看护、SQLite 持久化（schema v4 显式迁移）
├── operator_registry.py   # 算子注册表：real（llm_generic/http_request/logic_transform）/ simulated，mode 如实标注
├── llm_client.py          # LLM 韧性层：重试/信号量/超时 + SSE 流式
├── net_guard.py           # 出站防护：请求时 DNS 复检 + IP 固定直连（保 Host/SNI）
├── obs_logging.py         # JSON 结构化日志 + 密钥抹除 + request_id 上下文
├── metrics.py             # Prometheus 指标注册表
├── ast_validator.py       # 前端代码 AST 净化与自愈（hypothesis 模糊测试覆盖）
├── publisher.py           # 导出 ZIP / live-app 产物
├── models.py              # Pydantic 契约（WorkflowSnapshot v3.0.0 等）
├── static/vendor/         # Tailwind Play 本地化（live-app 无外部 CDN）
├── tests/                 # 184 用例：安全/引擎/持久化/算子/流式/多工作流/模糊/备份恢复…
├── scripts/               # smoke_ws.py / real_inference_test.py（真实推理 17 项）
└── Dockerfile             # 多阶段 + 非 root + HEALTHCHECK /healthz
```

## 启动

```bash
pip install -r requirements.txt
uvicorn perfect_main:app --host 127.0.0.0.0 --port 8000   # 实际用 --host 127.0.0.1 更安全
```

- Swagger UI：<http://localhost:8000/docs>
- 生产：必须设置 `AIGENT_ENV=production` + `AIGENT_ADMIN_TOKEN` + `LLM_API_BASE_ALLOWLIST`（缺失启动失败）。

## 测试

```bash
.venv/Scripts/python -m pytest -q                 # 184 用例
.venv/Scripts/python -m pytest -q --cov=...       # 见根 README 的覆盖率命令
.venv/Scripts/python -m ruff check .              # lint（ruff.toml）
```

## 接口全景（摘要）

- 工作流：`GET/POST /api/v1/workflows`、`GET/DELETE /api/v1/workflows/{id}`、`POST .../activate`、
  `GET/POST .../export|import`；拓扑编辑 `POST /workflow/nodes`、`PATCH /workflow/positions` 等。
- 运行/观测：`GET /runs`、`GET /checkpoints`、`POST /checkpoints/{id}/restore`、
  `GET /healthz`、`GET /readyz`、`GET /metrics`。
- 发布：`GET /publish/export-zip`、`GET /publish/live-app`、`GET /publish/live-app-url`（签名 URL 换取）。
- AI：`POST /workflow/ai-suggest`（LLM 严格 JSON 增量，服务端校验后才应用）。
- WS：`/ws/telemetry`（Origin 白名单 + 令牌；下行 snapshot/telemetry/node_update/node_stream/terminal_log）。

完整契约见《项目源码与架构文档.md》§4.3/§4.4；运维见 `docs/RUNBOOK.md`。
