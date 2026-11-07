# AIGENT-WORKFLOW STUDIO · 运行手册（RUNBOOK，T66）

> 目标读者：需要从零部署/日常运维本系统的工程师。文档中的每条命令均在 2026-11-07 实测过
（见 `docs/deploy-verified.md`、`docs/final-acceptance.md`）。

## 1. 启动 / 停止

### Docker Compose（推荐）

```bash
# 准备配置
cp .env.example .env          # 填 AIGENT_ADMIN_TOKEN（生产必填）与 LLM_*
# 启动（首次会构建镜像，backend 健康检查通过后 frontend 才启动）
AIGENT_ADMIN_TOKEN=<你的令牌> docker compose up -d --build
# 验证
docker ps                     # 两容器均 healthy
curl http://127.0.0.1:3000/   # 前端入口（nginx 非 root :8080 反代）
curl http://127.0.0.1:8010/healthz

# 停止 / 销毁
docker compose stop           # 保留容器
docker compose down           # 删容器（命名卷 aigent-data 保留）
docker compose down -v        # 连数据一起删（危险）
```

- 端口：前端入口 **3000**，后端直连 **8010**（compose 映射，运维/E2E 用）。
- 开发态前端：`cd frontend && npm run dev`（默认 5173，直连本机 8000 后端）。

### 本机裸跑（开发）

```bash
cd backend && .venv/Scripts/python -m uvicorn perfect_main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev
```

## 2. 环境变量

全量清单见 `.env.example`（含逐条说明）。关键项：

| 变量 | 作用 | 生产要求 |
|---|---|---|
| `AIGENT_ADMIN_TOKEN` | 管理令牌：写接口/设置/发布/WS 全部要求 | **必填**（缺失启动失败） |
| `LLM_API_BASE_ALLOWLIST` | api_base 主机白名单 | **必填**（缺失启动失败） |
| `AIGENT_ENV` | `production` 时启用上面的强制校验 | 建议设 production |
| `CORS_ORIGINS` | REST/WS 同源白名单（T11） | 含实际部署入口源 |
| `AIGENT_FORWARDED_ALLOW_IPS` | 信任的代理 IP（nginx 静态 IP 172.28.0.3） | compose 默认即可 |
| `LLM_API_KEY` | LLM 真实推理密钥 | 不配则相关节点降级（有 degraded 徽章） |
| `AIGENT_PUBLIC_READ` | 只读 GET 是否免令牌 | 生产保持未设 |

## 3. 日志

- **应用日志**：JSON 一行一条（ts/level/logger/message/request_id），uvicorn stdout →
  `docker compose logs aigent-backend`。`request_id` 与响应头 `X-Request-ID` 对应。
- **密钥安全**：api_key/令牌经 `SecretFilter` 抹除（`***REDACTED***`）。
- **健康**：`/healthz`（存活）与 `/readyz`（SQLite 可写 + 双循环心跳 <5s + 无连续失败），
  两者免鉴权，供 LB/编排器探测；`/metrics`（Prometheus 文本，配置令牌后必须带令牌）。

## 4. 常见故障

| 症状 | 原因 | 处置 |
|---|---|---|
| LLM 节点带「降级」徽章 | 429/5xx/超时（重试 2 次仍失败）或未配 key | 看 `[Warn] LLM` 日志；429→降低 `LLM_MAX_CONCURRENCY` 或在平台侧提额；超时→调大 `LLM_TIMEOUT_S` |
| WS 一直「重连中」 | 4401=令牌错/缺失；4403=Origin 不在 `CORS_ORIGINS` | 抽屉里更正令牌；把入口源加入 CORS_ORIGINS 后 `docker compose up -d aigent-backend` |
| `401 X-Admin-Token` | 写接口未带令牌 | 前端「大模型设置」抽屉填令牌（sessionStorage） |
| `/readyz` 503 | SQLite 不可写或引擎双循环死亡 | 看日志 `dag_loop_error`/`topology_restore_failed`；数据盘满/权限是最常见原因 |
| `database is locked` | 外部进程占用库 | 恢复流程见 `scripts/restore.md`；确认没有第二个后端指向同一库文件 |
| compose 起不来 `dependency failed to start` | backend unhealthy | `docker logs aigent-workflow-backend`，常见为生产守卫缺配置（见第 2 节） |

## 5. 令牌与密钥轮换

1. 生成新令牌：`python -c "import secrets;print(secrets.token_urlsafe(32))"`。
2. 更新 `.env` 的 `AIGENT_ADMIN_TOKEN` → `docker compose up -d aigent-backend`（滚动重启，秒级）。
3. 通知前端用户在「大模型设置」抽屉更新令牌（旧令牌立即失效）。
4. LLM key 轮换同路径（`LLM_API_KEY`）；或运行期热更：带令牌 `PUT /api/v1/settings/llm`
   （key 不会回显，仅返回末 4 位提示）。
5. 泄露应急：立即轮换 + 检查 `/metrics` 与访问日志中的异常来源 IP。

## 6. 备份与恢复

- 备份：`backend/.venv/Scripts/python scripts/backup.py --keep 7`
  （online backup，业务不中断；compose 部署先 `docker compose cp aigent-backend:/app/data/aigent_checkpoints.db ./`）
- 恢复：完整步骤与实测记录见 `scripts/restore.md`。
- 建议排程：每日一次 + 升级前一次；保留 7 份（可调）。

## 7. 升级与回滚

```bash
# 升级
git pull
docker compose up -d --build        # 重建镜像并滚动替换；数据在命名卷
# schema 迁移自动执行（schema_version 表，v1→v4 幂等）

# 回滚
git checkout <上一个tag或commit>
docker compose up -d --build
# 数据回滚：用升级前的备份走 scripts/restore.md
```

- 版本号见 `/healthz` 的 `version` 字段与前端标题栏。
- 升级前跑一次备份（第 6 节）。

## 8. 快速验收清单（部署后 3 分钟）

```bash
docker ps                                        # healthy × 2
curl -s http://127.0.0.1:3000/api/v1/workflow | head -c 80
curl -s http://127.0.0.1:8010/readyz             # "status":"ready"
curl -sI http://127.0.0.1:3000/ | grep -i x-frame  # DENY
```
