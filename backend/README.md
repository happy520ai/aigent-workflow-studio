# AIGENT-WORKFLOW STUDIO v2.8 · 后端服务

前端智能体工作流平台的 FastAPI 后端：**神经元 DAG 调度引擎 + WebSocket 实时遥测 + 算子库 REST API**。
技术栈：Python 3.11 + FastAPI + Asyncio + WebSockets + Pydantic v2 + Psutil。

## 目录结构

```text
backend/
├── requirements.txt      # 运行依赖
├── requirements-dev.txt  # 测试依赖（pytest）
├── models.py             # 全量数据模型与状态契约 (Pydantic v2)
├── engine.py             # 异步神经元 DAG 调度引擎与 WebSocket 广播中心
├── main.py               # FastAPI 路由、生命周期与实时遥测服务入口
├── conftest.py           # pytest 导入路径垫片
├── pytest.ini
├── tests/                # 四层测试套件：models / engine / REST API / WebSocket
└── scripts/smoke_ws.py   # 真实服务冒烟脚本
```

## 启动（三行）

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- 交互式 API 文档（Swagger UI）：<http://localhost:8000/docs>
- 实时遥测 WebSocket：`ws://localhost:8000/ws/telemetry`
- 可选真实大模型：设置环境变量 `LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL`
  （未配置时自动走内置毫秒级神经仿真；外部模型不可达时降级为本地内核并记录 `[Warn]` 日志）

## 测试

```bash
pip install -r requirements-dev.txt
python -m pytest -v        # 四层套件：models / engine / REST API / WebSocket

# 真实服务冒烟（先另开终端启动 uvicorn）
python scripts/smoke_ws.py http://127.0.0.1:8000
```

## 与原架构文档的唯一差异

`engine.py` 的 `handle_control(RESET)` 分支补了一行 `self._debug_step_gate.set()`：
原文档在「调试单步挂起后点重置」时只复位了暂停门，工作循环会永远卡死在单步门上
（状态栏显示"运行中"但引擎实际冻结）。该行与 RUN 分支的处理完全对称，其余代码与文档逐字一致。
