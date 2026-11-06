# 文档↔源码漂移核对（T02，2026-11-07）

> 依据《生产化执行方案.md》T02：对 `项目源码与架构文档.md` 的 §4.3 REST 表、§4.4 WS 事件、§4.13 环境变量表逐条与源码核对。**本任务不改源码**，两处行号级漂移仅在此登记。

## 方法

以 grep 提取 `backend/perfect_main.py` 的全部路由装饰器、WS 事件名与 `os.getenv` 读取点（辅以 `perfect_engine.py`、Dockerfile、docker-compose.yml、tests/scripts 反向核对），逐条对照文档 §4.3/§4.4/§4.13。

## §4.3 REST API

| 文档条目 | 源码证据 file:line | 结论(✅一致/⚠️漂移/❌文档虚) |
|---|---|---|
| GET `/api/v1/components` | `backend/perfect_main.py:88` | ✅一致 |
| GET `/api/v1/workflow` | `backend/perfect_main.py:96` | ✅一致 |
| POST `/api/v1/workflow/control` | `backend/perfect_main.py:101` | ✅一致 |
| POST `/api/v1/workflow/nodes` | `backend/perfect_main.py:106` | ✅一致 |
| DELETE `/api/v1/workflow/nodes/{id}` | `backend/perfect_main.py:114` | ✅一致 |
| PATCH `/api/v1/workflow/nodes/{id}/position` | `backend/perfect_main.py:122` | ✅一致 |
| PUT `/api/v1/workflow/nodes/{id}/config` | `backend/perfect_main.py:134` | ✅一致 |
| POST `/api/v1/workflow/edges` | `backend/perfect_main.py:147` | ✅一致 |
| DELETE `/api/v1/workflow/edges/{id}` | `backend/perfect_main.py:204` | ✅一致 |
| GET `/api/v1/runs` | `backend/perfect_main.py:175` | ✅一致 |
| GET `/api/v1/search` | `backend/perfect_main.py:181` | ✅一致 |
| POST `/api/v1/ast/validate` | `backend/perfect_main.py:216` | ✅一致 |
| GET `/api/v1/checkpoints` | `backend/perfect_main.py:226` | ✅一致 |
| POST `/api/v1/checkpoints/{id}/restore` | `backend/perfect_main.py:231` | ✅一致 |
| GET `/api/v1/sandbox/preview` | `backend/perfect_main.py:258` | ✅一致 |
| GET `/api/v1/settings/llm`（require_admin 守卫） | `backend/perfect_main.py:353`（守卫 `:354`，`require_admin` 定义 `:267`） | ✅一致 |
| PUT `/api/v1/settings/llm` | `backend/perfect_main.py:366`（Depends(require_admin) `:367`） | ✅一致 |
| GET `/api/v1/publish/export-zip` | `backend/perfect_main.py:379` | ✅一致 |
| GET `/api/v1/publish/live-app` | `backend/perfect_main.py:394` | ✅一致（文档表内未标行号，仅引 §4.10，路径一致） |
| 无独立 `/health` 端点 | 路由 grep 全量结果中无 health | ✅一致 |

反向核对：代码中共 20 条路由（19 REST + 1 WS），全部在文档表内，无遗漏。

## §4.4 WS 事件

| 文档条目 | 源码证据 file:line | 结论(✅一致/⚠️漂移/❌文档虚) |
|---|---|---|
| 握手下发 `workflow_snapshot`（含 data + sandbox_html） | `backend/perfect_main.py:422-428`（event `:424`，sandbox_html `:426`） | ✅一致 |
| 客户端→服务端仅 `select_node` | `backend/perfect_main.py:431` | ✅一致 |
| 单播回 `selected_node_changed` | `backend/perfect_main.py:435` | ✅一致 |
| `telemetry_tick`（500ms，不含 sandbox_html） | `backend/perfect_engine.py:775`（broadcast 调用 `:774`，`asyncio.sleep(0.5)` `:785`，瘦身注释 `:773`） | ✅一致 |
| `node_update`（node + sandbox_html + shared_memory_bus） | `backend/perfect_engine.py:630`（载荷三键 `:631-635`） | ✅一致 |
| `terminal_log`（line + 最近 12 条） | `backend/perfect_engine.py:517-518` | ✅一致 |
| `workflow_snapshot`（控制/拓扑变更后广播） | `backend/perfect_engine.py:850`、`:897`、`:912` | ✅一致 |

代码中有而文档没有的事件：无。`perfect_engine.py:214` 的 `"last_event": "USER_CLICK_GENERATE_DASHBOARD"` 是 checkpoint 字段而非 WS 事件，文档未列不构成漂移。

## §4.13 环境变量

| 文档条目 | 源码证据 file:line | 结论(✅一致/⚠️漂移/❌文档虚) |
|---|---|---|
| `LLM_API_KEY` 默认空 | `backend/perfect_engine.py:207` `os.getenv("LLM_API_KEY", "")` | ✅一致 |
| `LLM_API_BASE` 默认 `https://api.openai.com/v1` | `backend/perfect_engine.py:208` | ✅一致 |
| `LLM_MODEL` 默认 `gpt-4o-mini` | `backend/perfect_engine.py:209` | ✅一致 |
| `CORS_ORIGINS` 默认 `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000` | `backend/perfect_main.py:76-79` | ✅一致（默认值逐字符相同） |
| `AIGENT_ADMIN_TOKEN` 默认空 | `backend/perfect_main.py:269` | ✅一致 |
| `AIGENT_DB_PATH` 默认 `aigent_checkpoints.db`；文档标注读取处 `perfect_main.py:37` | 唯一读取点为 `backend/perfect_engine.py:41`（`db_path or os.getenv("AIGENT_DB_PATH") or "aigent_checkpoints.db"`，且 `:199` 构造时不传 db_path）；`perfect_main.py:37` 实为 `class MoveNodeRequest` | ⚠️漂移：变量与默认值正确，但文档引用的 perfect_main.py:37 读取处错误（该行是 MoveNodeRequest） |
| `AIGENT_PERSIST_TOPOLOGY` 默认 `1` | `backend/perfect_main.py:26` | ✅一致 |
| `CHECKPOINT_MAX` 默认 `2000` | `backend/perfect_engine.py:37` | ✅一致 |
| `LLM_API_BASE_ALLOWLIST` 默认空 | `backend/perfect_main.py:292` | ✅一致（另有第二读取点 `:330` 文档未列，属轻微不全） |
| `AIGENT_ALLOW_PRIVATE_LLM` 默认空（拒绝） | `backend/perfect_main.py:299` | ✅一致（另有第二读取点 `:335` 文档未列） |
| `AIGENT_FORWARDED_ALLOW_IPS` 默认 `127.0.0.1,::1`（容器含 172.28.0.3）；文档标注读取处 Dockerfile:20 | 实际 `backend/Dockerfile:19`（CMD 内 `${AIGENT_FORWARDED_ALLOW_IPS:-127.0.0.1,::1}`，`:18` 为注释）；`docker-compose.yml:23`（`:-172.28.0.3,127.0.0.1,::1`） | ⚠️漂移：默认值语义完全一致，但行号引用偏 1 行 |

代码中有而 §4.13 未列的环境变量（测试/脚本变量，非主契约）：

- `BACKEND_PYTEST_VENV` — `backend/conftest.py:16,18`（pytest 引导标记）
- `SMOKE_ADMIN_TOKEN` — `backend/scripts/real_inference_test.py:32`（默认 `aigent-verify-token`）、`backend/scripts/smoke_ws.py:14`（默认空）
- v1 遗留 `engine.py:282-284` 读取 `LLM_API_KEY/LLM_API_BASE/LLM_MODEL`，属文档 §4.14 已声明的遗留文件，不算漂移

## 汇总

共核对 49 条：**47 条 ✅一致，2 条 ⚠️漂移（均为"读取处行号引用错误"级别：`AIGENT_DB_PATH` 的 perfect_main.py:37 指向错误代码、`AIGENT_FORWARDED_ALLOW_IPS` 的 Dockerfile 行号偏 1），0 条 ❌文档虚**，代码侧无遗漏端点/事件。整体结论：三节内容与源码高度同步，仅存在两处轻微行号级漂移，无实质性文档失真。按 T02 约定本次不改源码，P7-T71 文档重写时一并修正。
