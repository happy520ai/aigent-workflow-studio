# AIGENT-WORKFLOW STUDIO v2.8 · 神经元工作流平台

前端 React 18 + TS + Vite（5173）· 后端 FastAPI（8000）。
现役入口：后端 `backend/perfect_main.py` + `backend/perfect_engine.py`（v1 `main.py`/`engine.py` 仅保留兼容）。
完整结构说明见 [代码结构图.txt](./代码结构图.txt)。

## 快速启动

```bash
# 后端（虚拟环境）
cd backend
.venv/Scripts/python -m uvicorn perfect_main:app --port 8000

# 前端
cd frontend
npm install && npm run dev   # :5173

# 测试
cd backend && .venv/Scripts/python -m pytest -q
cd frontend && npm run build
node test/verify-perfect-workbench.js
```

## 环境变量

### 大模型与安全

| 变量 | 说明 | 默认 |
|---|---|---|
| `LLM_API_KEY` | 大模型密钥（任何响应绝不回显原文，仅露末 4 位） | 空（走内置模板） |
| `LLM_API_BASE` | 大模型接口地址 | `https://api.openai.com/v1` |
| `LLM_MODEL` | 模型名 | `gpt-4o-mini` |
| `AIGENT_ADMIN_TOKEN` | 设置接口管理令牌；设置后请求必须带 `X-Admin-Token` 头，否则 401 | 空（仅允许本机回环访问，否则 403） |
| `LLM_API_BASE_ALLOWLIST` | api_base 主机白名单（逗号分隔），配置后跳过 DNS 内网校验 | 空 |
| `AIGENT_ALLOW_PRIVATE_LLM` | `=1` 放行解析到内网/保留地址的 api_base | 空（默认拒绝） |
| `CORS_ORIGINS` | CORS 白名单（逗号分隔） | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000` |

### 持久化

| 变量 | 说明 | 默认 |
|---|---|---|
| `AIGENT_DB_PATH` | SQLite 断点库路径 | `aigent_checkpoints.db`（工作目录） |
| `AIGENT_PERSIST_TOPOLOGY` | `=1` 启动时还原上次拓扑，并在增删节点/连线、位置/配置变更、RESET 后落库 | `1` |
| `CHECKPOINT_MAX` | 断点库上限，超出按时间倒序剪枝 | `2000` |

### 前端接线（frontend/.env 可覆盖）

| 变量 | 说明 | 默认 |
|---|---|---|
| `VITE_API_BASE` | REST 基址 | `http://localhost:8000/api/v1` |
| `VITE_WS_URL` | WebSocket 地址 | `ws://localhost:8000/ws/telemetry` |

## 已知边界

- 12 个算子 + 1 个兜底均为内置模拟（WS/REST 返回 `mode: "simulated"` 如实标注），仅 ui_generation / agent_codegen 在配置了 `LLM_API_KEY` 时真实外呼大模型。
- api_base 的 DNS 校验无法完全防 DNS rebinding（解析与请求之间存在时间差）。
- ECG 心电波形为纯装饰性随机生成，非真实指标；CPU/内存为 psutil 真实采样。
