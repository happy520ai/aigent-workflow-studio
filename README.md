# AIGENT-WORKFLOW STUDIO v3.0.0

神经元式智能体工作流平台：React 工作台（赛博蜘蛛 HUD 设计语言）+ FastAPI 动态 DAG 引擎 +
12+ 算子内核（真实 LLM / HTTP / 逻辑变换 + 明确标注的模拟算子）+ SQLite 时间旅行 + 多工作流。

> 生产化改造（P0–P7）已完成：安全加固、可观测、多工作流、真实算子、E2E、CI、Docker。
> 架构总览见《项目源码与架构文档.md》；运维见 `docs/RUNBOOK.md`。

## 快速开始（Docker Compose，推荐）

```bash
cp .env.example .env                # 填 AIGENT_ADMIN_TOKEN 等配置
docker compose up -d --build
docker ps                           # 等待两容器 healthy
# 前端入口 http://127.0.0.1:3000 · 后端直连 http://127.0.0.1:8010/healthz
```

本机开发：

```bash
cd backend && .venv/Scripts/python -m uvicorn perfect_main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev          # http://localhost:5173
```

## 能力一览

- **动态 DAG 引擎**：Kahn 分层编译 + 环路兜底反馈层；节点执行计数/耗时/错误隔离；运行记录持久化（重启不丢）。
- **真实算子**：`llm_generic`（模板变量取自上游输出）、`http_request`（SSRF 防护 + IP 固定直连）、`logic_transform`（点路径/模板映射，无 eval）；其余算子 `mode=simulated` 如实标注。
- **LLM 韧性**：重试（429/5xx/超时，指数退避+抖动）、并发信号量、可配超时、SSE 流式输出（WS `node_stream` 增量）、降级徽章。
- **多工作流**：CRUD / 激活切换 / JSON 导入导出（类型白名单 + 环检测）/ AI 生成节点（严格 JSON 增量 + 服务端校验）/ Kahn 自动布局。
- **安全**：全局管理令牌（X-Admin-Token + WS token + 短期签名 URL）、WS Origin 白名单、限流与体积上限、安全响应头、DNS rebinding 防护、日志密钥抹除。
- **可观测**：`/healthz` `/readyz` `/metrics`（Prometheus）；JSON 结构化日志带 X-Request-ID。
- **时间旅行**：每轮 DAG 落 SQLite 断点，含拓扑回滚；前端控制台一键恢复。

## 测试与质量

```bash
cd backend && .venv/Scripts/python -m pytest -q              # 184 用例
cd backend && .venv/Scripts/python -m pytest -q \
  --cov=perfect_engine --cov=perfect_main --cov=ast_validator \
  --cov=operator_registry --cov=llm_client --cov=metrics \
  --cov=net_guard --cov=obs_logging --cov-report=term        # 核心模块 ≥80%（实测 90%）
cd frontend && npm test                                       # vitest 16 用例
cd frontend && npx playwright test                            # E2E 4 场景（自起前后端）
node test/verify-perfect-workbench.js                         # 结构校验 47:0
```

CI（GitHub Actions，`.github/workflows/ci.yml`）：后端 ruff + pytest(覆盖率门槛 80%) + pip-audit；
前端 npm audit + tsc/build + vitest；双镜像构建；E2E 手动触发。

## 目录

```
backend/    FastAPI 引擎与测试（perfect_main / perfect_engine / operator_registry / net_guard / llm_client / metrics / obs_logging）
frontend/   React 工作台（Workbench 组合根 + components/ hooks/ utils/）+ e2e/
docs/       baseline / doc-drift / security-scan / deploy-verified / RUNBOOK / lighthouse
scripts/    backup.py / ws_smoke.py / restore.md
test/       verify-perfect-workbench.js（结构校验）
```

## 许可与密钥

- `.env`（真实 key）不入库；模板见 `.env.example`。
- 生产必读：`docs/RUNBOOK.md` 第 2 节（AIGENT_ENV=production 强制 AIGENT_ADMIN_TOKEN 与 LLM_API_BASE_ALLOWLIST）。
