# 安全扫描报告（T16，2026-11-07，P1 收口）

## 1. 依赖漏洞扫描

### 后端 pip-audit
- 工具：pip-audit（已加入 `backend/requirements-dev.txt`）
- **发现：starlette 0.38.6 存在 14 条已知漏洞（PYSEC-2026-161/248/249/1941/1943/2280/2281 等，高危必修）**
- **修复**：`fastapi 0.115.0 → 0.162.0`、`pydantic 2.9.2 → 2.14.3`、`starlette 0.38.6 → 1.10.0`（显式钉版）
- 回归：升级后全量 pytest 113 用例全绿（零用例改动）
- 复扫：`python -m pip_audit -r requirements.txt` → **No known vulnerabilities found**

### 前端 npm audit
- 命令：`npm audit --omit=dev`
- 结果：**found 0 vulnerabilities**

## 2. 密钥扫描

- 工具：pm-mcp `audit_security`（gitleaks 本机未安装；本仓库已 git init，密钥扫描以该工具 + git 追踪核对为准）
- git 追踪核对：`git ls-files | grep -E "\.db$|(^|/)\.env"` → **0 命中**（.env / .env.local / *.db 均未入库，.gitignore 覆盖）
- 审计发现 9 条，全部处置完毕（0 open）：

| 发现 | 定性 | 处置 |
|---|---|---|
| .env / frontend/.env.local 存在 | 本机配置文件 | accepted：未入库且 .gitignore 覆盖；T62 提供 .env.example，T63 删除 .env.local |
| ast_validator.py "eval(" | **误报** | accepted：是拦截 eval() 的防御性正则（DANGEROUS_PATTERNS），该文件是净化器本体 |
| real_inference_test.py 疑似 key | **误报** | accepted：故意注入的无效密钥（T7 错误密钥降级用例），非真实凭据 |
| static/vendor/tailwindcss-play.js ×3 | **误报** | accepted：Tailwind Play 3.4.16 官方 minified 构建，压缩产物撞 SQL 关键字正则；不接触数据库 |
| tests 内硬编码 token ×2 | **误报** | accepted：测试夹具假凭据（验证不回显/鉴权矩阵），非真实凭据 |

## 3. 遗留债务

- 无高危未处理项。
- 说明：starlette 1.10.0 的 TestClient 提示 `httpx` 传参已弃用（建议 httpx2）——仅 deprecation 警告，现版可用，留待 P5 测试体系阶段评估，不阻塞。

## 4. P1 期间落地安全控制（对照方案 T10–T15）

- T10 全局鉴权中间件（X-Admin-Token / 签名 URL / fail-closed 403）
- T11 WS 握手鉴权（Origin 白名单 4403 / token 4401）
- T12 LLM api_base 请求时解析复检 + IP 固定直连（防 DNS rebinding）
- T13 令牌桶限流（写 60/min、严格面 10/min）+ 体积/数量上限（413）
- T14 安全响应头（nosniff / no-referrer / XFO DENY，live-app 豁免）+ nginx CSP
- T15 live-app CSP 收紧（Tailwind Play 本地化，去外部 CDN 与 script 'unsafe-inline'）
