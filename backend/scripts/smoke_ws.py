"""真实 uvicorn 服务冒烟验证：REST 契约 + WebSocket 实时流（独立于 pytest 套件）

用法：先启动 uvicorn，再执行
    python scripts/smoke_ws.py http://127.0.0.1:8000
"""
import json
import os
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
# 可选管理令牌：容器/反代部署设置了 AIGENT_ADMIN_TOKEN 时用它通过设置接口守卫
ADMIN_TOKEN = os.environ.get("SMOKE_ADMIN_TOKEN", "")
WS_URL = BASE.replace("http", "ws", 1) + "/ws/telemetry"

failures = []
events = {}


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


def rest(method, path, payload=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if ADMIN_TOKEN:
        headers["X-Admin-Token"] = ADMIN_TOKEN
    req = urllib.request.Request(
        BASE + path,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------- REST 契约 ----------
snap = rest("GET", "/api/v1/workflow")
check("GET /api/v1/workflow 版本 v3.0.0", snap["version"] == "v3.0.0")
check("画布 5 个神经元节点", len(snap["nodes"]) == 5)
check("4 条神经突触连线", len(snap["edges"]) == 4)

comps = rest("GET", "/api/v1/components?q=%E8%A7%A6%E5%8F%91")  # q=触发
check("组件库中文搜索（触发→1 项：模板版仅匹配 name/name_en）", len(comps) == 1)

put = rest("PUT", "/api/v1/workflow/nodes/node_ui_gen/config",
           {"name": "smoke", "role": "patched-by-smoke"})
check("PUT 节点 JSON 配置热更新", put["config_json"].get("role") == "patched-by-smoke")

# ---------- 新增契约 ----------
runs = rest("GET", "/api/v1/runs?limit=5")
check("GET /api/v1/runs 返回运行记录列表", isinstance(runs, list))

from urllib.error import HTTPError

try:
    rest("POST", "/api/v1/workflow/edges", {"source": "node_ui_gen", "target": "node_ui_gen"})
    check("POST /edges 自环应 400", False)
except HTTPError as e:
    check("POST /edges 自环返回 400", e.code == 400)

llm = rest("GET", "/api/v1/settings/llm")
check("GET /settings/llm 不回显 api_key 字段", "api_key" not in llm)

# ---------- WebSocket 实时流（引擎全速运行中） ----------
from websockets.sync.client import connect

try:
    with connect(WS_URL, open_timeout=5) as ws:
        ws.send(json.dumps({"type": "select_node", "node_id": "node_ui_gen"}))
        wanted = {"workflow_snapshot", "telemetry_tick", "terminal_log", "selected_node_changed"}
        deadline = time.time() + 12
        while time.time() < deadline and not wanted <= set(events):
            msg = json.loads(ws.recv(timeout=4))
            events.setdefault(msg["event"], msg)
except Exception as exc:
    print(f"[FAIL] WebSocket 连接/接收异常: {exc}")

check("WS 首连下发完整快照", "workflow_snapshot" in events)
tick = events.get("telemetry_tick")
check("WS 500ms 遥测节拍（CPU/内存/ECG/雷达/突触）", tick is not None)
check("telemetry_tick 不含 sandbox_html（A8 遥测瘦身）", bool(tick) and "sandbox_html" not in tick["data"])
check("WS 终端日志实时流", "terminal_log" in events)
sel = events.get("selected_node_changed")
check("WS select_node 选中回执", bool(sel) and sel["data"]["id"] == "node_ui_gen")

# ---------- 控制指令闭环 ----------
try:
    check("POST control 暂停", rest("POST", "/api/v1/workflow/control",
                                    {"action": "pause"})["project_status"] == "已暂停")
    check("POST control 恢复运行", rest("POST", "/api/v1/workflow/control",
                                       {"action": "run"})["project_status"] == "运行中")
except Exception as exc:
    print(f"[FAIL] 控制指令异常: {exc}")

print(f"\n冒烟结果: {'全部通过' if not failures else str(len(failures)) + ' 项失败: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
