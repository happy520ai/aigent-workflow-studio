# 部署实测记录（T61，2026-11-07）

环境：Windows 10 · Docker 29.4.0 · Docker Compose v5.1.2 · 本仓库 master。

## 命令与结果

| 步骤 | 命令 | 结果 |
|---|---|---|
| 构建+启动 | `AIGENT_ADMIN_TOKEN=deploy-test-token docker compose up -d --build` | backend Healthy → frontend 依赖门控启动 |
| 健康检查 | `docker ps` | 两容器均 `healthy`（healthcheck 生效） |
| 后端直连 | `curl http://127.0.0.1:8010/healthz` | `{"status":"ok","version":"2.8.0-ultimate"}` |
| 前端入口 | `curl -I http://127.0.0.1:3000/` | 200 + nosniff/no-referrer/XFO DENY/CSP |
| REST 反代 | `curl http://127.0.0.1:3000/api/v1/workflow` | 完整快照 JSON（nginx → backend:8000） |
| WS 反代 | `backend/.venv/Scripts/python scripts/ws_smoke.py "ws://127.0.0.1:3000/ws/telemetry?token=deploy-test-token" "http://127.0.0.1:3000"` | `WS_UPGRADE_OK first_event= workflow_snapshot` |
| Origin 白名单 | 同上但 `Origin=http://evil.example.com` | `4403` 关闭（T11 生效） |
| 鉴权 | 带令牌 vs 无令牌 | 带令牌 200；无令牌写操作 401 |
| 数据卷 | 命名卷 `aigent-data`（Windows bind mount 有陈旧锁文件问题，改命名卷） | 正常 |
| **重启持久化** | 加 NLU 节点 → `docker compose restart aigent-backend` → 再查 | `nodes after restart: 6, has NLU: true` |

## 过程中修复

1. Windows bind mount + WAL 在非 root 容器下报 readonly → **compose 改命名卷 `aigent-data`**（生产上亦更规范）。
2. nginx `location` 有自己的 `add_header` 时不继承 server 级 → index/assets/api 三处补齐安全头（否则首页安全头丢失）。
3. WS 经 nginx 的 Origin 白名单：compose 增 `CORS_ORIGINS` 可配置并默认含部署入口源。

## 结论

单机 compose 部署全链路可用：构建 → 健康门控 → REST/WS 反代 → 鉴权 → 安全头 → 数据持久化，全部按方案验收通过。
