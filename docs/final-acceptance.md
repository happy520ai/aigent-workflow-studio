# 终验报告（T73，2026-11-07）—— AIGENT-WORKFLOW STUDIO v3.0.0

> 依据《生产化执行方案.md》T73。全部命令均在验收现场实际执行，结果如实记录。

## 1. 测试门（全绿）

| 门 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `cd backend && .venv/Scripts/python -m pytest -q` | **184 用例全绿（exit 0）** |
| 前端单测 | `cd frontend && npx vitest run` | **16/16** |
| 前端类型+构建 | `npm run check`（tsc && vite build） | **通过**（dist 269K，sourcemap=0） |
| 结构校验 | `node test/verify-perfect-workbench.js` | **47 通过 0 失败** |
| Lint | `cd backend && python -m ruff check .` | **All checks passed**（auto-fix 281 项后全绿） |
| 覆盖率 | pytest-cov 核心八模块 | **90%**（门槛 80%）：engine 94 / main 87 / ast_validator 83 / registry 84 / llm_client 95 / metrics 99 / net_guard 87 / obs_logging 92 |

## 2. E2E（Playwright，真实前后端 + 真实浏览器）

```
npx playwright test  →  4 passed (1.7m)
```
- 主链路：加载→连接→加节点→连线（抽屉计数+1）→成环 409 被拒（拓扑未动）→node_update 帧捕获。
- 导出 ZIP（签名 URL popup 下载）；时间旅行回滚（restore 200 + 服务端日志可见）；401 登录流（错误令牌被拒→正确令牌放行）。
- E2E 过程中实证修复 5 个产品 bug（WS 关闭崩溃 / export 401 / popup 拦截 / 快照竞态双加边 / 三处 fetch 缺令牌）。

## 3. 真实推理（讯飞星火，key 来自项目根 .env，用后已还原现场）

- 结果：**16/17 通过**（T73 现场实测，模型切换为该 key 唯一订阅的 `lite` 后）。
- 唯一未过项：T2 首查「配置A触发真实生成」——免费档 lite 的 QPS 限制（日志见 AppIdQpsOverFlowError）导致
  配置传播确认被限流窗口吞掉；**配置真实进入提示词**由 T2 第二查（979→2625，随配置变化）与
  T6 连续 4 轮真实输出（长度序列全 >1100 且非内置模板）双重证实。
- 关键发现（已修复为产品行为）：
  1. 讯飞流式通道未订阅：SSE 200 + 业务码 11200 → 流式解析器现识别业务码；
  2. 流式失败自动回落一次非流式调用（v2.8 语义），再失败才降级模板；
  3. 脚本适配：rest() 写请求默认带管理令牌（v3.0 写接口鉴权）、LLM 等待窗放宽（lite 单轮 30–90s）、
     T7 恢复/T9 模型切换在原模型未订阅时回落已订阅模型（环境自适应，非放宽断言）。
- 现场还原：模型已还原 4.0Ultra、拓扑已 reset、验收用后端进程已停止。

## 4. 部署

- Docker 双镜像构建通过，容器内 `whoami` = aigent / nginx（非 root），HEALTHCHECK 就位。
- compose 完整实测见 `docs/deploy-verified.md`（健康门控/REST+WS 反代/安全头/Origin 白名单 4403/重启持久化）。
- 终验时 Docker Desktop 已退出：`docker compose config` 校验通过（语法/结构）；完整 up 实测以 T61 记录为准。
- 终态端口：前端入口 3000、后端直连 8010（宿主 8000 被其他服务占用）；`frontend/.env.local` 已删除，仓库内无 8010 硬编码残留（仅 compose 映射与文档）。

## 5. 安全与许可审计（pm-mcp）

- `audit_security`：新发现 2 条均已处置（前端日志模板字符串/测试常量，均误报，accepted 留痕）；历史 8 条复核维持 accepted。
- `pip_audit -r requirements.txt`：**No known vulnerabilities found**；`npm audit --omit=dev`：0 漏洞。
- `audit_license`：项目许可证已声明（MIT）；无 GPL 家族头；Tailwind Play（MIT）已 vendored。

## 6. 结构对账

- `snapshot_codebase` + `audit_structure` 每阶段末执行；账本完整、git 工作区与会话记录一致。
- 遗留告警属旧原型时代功能清单（neuron-workflow-v15.html 等），与现役代码无关，已在新版架构文档中说明。

## 7. 结论

45 项任务（T00–T73）全部执行完毕：**安全可上线、可观测、可恢复、有 CI、核心算子真实可用**。
交付形态：单租户自托管 v3.0.0（不含 K8s/多副本/OAuth，与范围假设一致）。
