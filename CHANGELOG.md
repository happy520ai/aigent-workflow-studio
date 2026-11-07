# CHANGELOG

## 3.0.0（2026-11-07）—— 生产化改造（P0–P7）

依据《生产化执行方案.md》45 项任务全量执行；全程逐任务提交、每步全量回归。

### P0 基线与版本控制
- git init（.gitignore 覆盖 db/env/产物）；基线 83 用例 + build + verify 47:0 存档 `docs/baseline.txt`；文档↔源码核对 `docs/doc-drift.md`。

### P1 安全加固
- 全局鉴权中间件（X-Admin-Token；/publish 与 /settings 敏感面；AIGENT_PUBLIC_READ；未配置令牌非回环 403；live-app/export-zip 短期签名 URL）。
- WS 握手鉴权：Origin 白名单 4403 / token 4401。
- DNS rebinding 修复：请求时解析复检 + 按校验 IP 直连（net_guard.py，保 Host/SNI）。
- 令牌桶限流（写 60/min、严格面 10/min）+ ast code 512KB / config 64KB / 节点 200 / 连线 500 上限。
- 安全响应头 + nginx CSP；live-app Tailwind 本地化（去外部 CDN 与 script unsafe-inline）。
- pip-audit 清零 14 个 starlette 漏洞（fastapi 0.162 / starlette 1.10 / pydantic 2.14）；`docs/security-scan.md`。

### P2 可靠性与可观测
- /healthz /readyz（SQLite+双循环+心跳）；SQLite WAL+busy_timeout+写锁+schema_version 显式迁移（v1→v4）。
- JSON 结构化日志 + X-Request-ID + 密钥抹除；/metrics（Prometheus：节点/LLM/轮次直方图/WS gauge）。
- LLM 韧性层 llm_client.py（重试/信号量/超时/降级徽章）；优雅关闭与循环看护（503 语义）。
- runs 运行记录持久化；ECG 波形改真实 DAG 轮延迟。

### P3 核心能力
- 真实算子框架（llm_generic / http_request / logic_transform，mode 如实标注）；SSE 流式 node_stream。
- 多工作流（schema v4 + WorkflowState 属性委托 + 切换器）；JSON 导入导出（校验拒绝 5 路径）。
- AI 生成节点 ai-suggest（严格 JSON 增量，恶意输出全拒，测试全 mock）；Kahn 自动布局。

### P4 前端工程化
- Workbench 1722→~880 行拆分（types/hooks×3/components×7）；删除 7 个零引用遗留；noUnused 全开。
- ErrorBoundary + 全局 toast + WS 重连状态条；401 自救流；撤销/重做 + 框选 + 缩放平移。
- 可访问性（focus-visible、prefers-reduced-motion 三层关停、aria、窄屏浮层；Lighthouse a11y 100/100）。
- 构建：sourcemap=0 + 分包（dist 269K）。

### P5 测试体系
- vitest 16 用例（布局/config/日志分级/WS 退避）；Playwright E2E 4 场景（途中修复 5 个真实产品 bug）。
- pytest-cov 核心模块 90%（门槛 80%）；hypothesis AST 模糊测试（3 不变量 ×700 样本）；verify 脚本升级为文件存在性+锚点。

### P6 部署运维
- Docker 加固（多阶段/非 root/HEALTHCHECK/npm ci/资源限制）；compose 完整实测（`docs/deploy-verified.md`，含 WS 反代/Origin/持久化）。
- .env.example + AIGENT_ENV=production 启动守卫；备份/恢复（scripts/backup.py + restore.md + 回归测试）；GitHub Actions CI（lint/test/audit/docker/e2e）；RUNBOOK。

### P7 收尾
- 删除 v1 遗留（main/engine/test_api/test_engine/test_websocket/test_workflow_e2e）；等价覆盖迁移。
- 文档按最终代码重写（README/backend/架构文档/RUNBOOK）；版本统一 3.0.0。

### 兼容性说明
- WorkflowSnapshot.version 由 v2.8 → v3.0.0（前端契约同步）。
- 导出 ZIP 文件名 aigent-bundle-v3.0.0.zip。
- 写接口在配置令牌后一律要求 X-Admin-Token（旧匿名写法会 401）。
