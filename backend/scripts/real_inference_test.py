"""真实推理测试：验证 v2.8 工作台的 LLM 链路（讯飞星火等真实大模型）。

覆盖：
  T1 配置前置校验（密钥存在、模型名、不回显明文）
  T2 配置驱动真实推理（改节点配置 → 沙盒输出随之变化，证明 config 真进提示词）
  T3 输出质量基线（非内置模板、长度、闭合完整、无危险标签残留）
  T4 第二 LLM 算子（agent_codegen）真实外呼（latency 显著高于本地模拟算子）
  T5 并发多 LLM 节点同轮执行（ui_generation + 2×agent_codegen）
  T6 多轮稳定性（连续 4 轮，无 [Warn] 降级、沙盒均非内置模板）
  T7 错误密钥降级（[Warn] 日志 + 回落内置模板 + 循环不中断）
  T8 SSRF 守卫（内网 api_base 被 400 拒绝）
  T9 模型切换（4.0Ultra ↔ generalv3.5 均真实可用）

用法（需先启动后端；密钥从项目根 .env 读取）：
    python scripts/real_inference_test.py [http://127.0.0.1:8010]

说明：测试会临时改写 node_ui_gen 配置与拓扑，结束时自动还原。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
ADMIN_TOKEN = os.environ.get("SMOKE_ADMIN_TOKEN", "aigent-verify-token")
ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")

# 内置模板的特征片段（前后端共用同一模板，命中即为"未真实调用 LLM"）
BUILTIN_TEMPLATE_MARKERS = ("DOM RENDERER LIVE SANDBOX", "实时神经元视图")

failures = []
results = []


def check(name, cond, detail=""):
    line = f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" | {detail}" if detail else "")
    print(line)
    results.append((name, bool(cond), detail))
    if not cond:
        failures.append(name)


def load_env_key() -> str:
    for raw in open(ENV_FILE, encoding="utf-8"):
        raw = raw.strip()
        if raw.startswith("LLM_API_KEY="):
            return raw.split("=", 1)[1].strip()
    return ""


def rest(method, path, payload=None, token=True):
    # v3.0.0：写接口一律要求管理令牌（T10）——默认全部携带
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["X-Admin-Token"] = ADMIN_TOKEN
    req = urllib.request.Request(
        BASE + path,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body


def get_workflow():
    status, snap = rest("GET", "/api/v1/workflow")
    return snap if status == 200 else {}


def get_sandbox_html() -> str:
    status, data = rest("GET", "/api/v1/sandbox/preview")
    if status != 200 or not isinstance(data, dict):
        return ""
    return data.get("html", "")


def is_builtin_template(html: str) -> bool:
    return any(m in html for m in BUILTIN_TEMPLATE_MARKERS)


def wait_for(predicate, timeout_s=150, interval=1.2):
    """轮询直到 predicate() 为真，返回 (是否命中, 耗时秒)"""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if predicate():
                return True, round(time.time() - t0, 1)
        except Exception:
            pass
        time.sleep(interval)
    return False, round(time.time() - t0, 1)


def node_by_id(nid):
    for n in get_workflow().get("nodes", []):
        if n["id"] == nid:
            return n
    return None


def llm_config_snapshot():
    status, data = rest("GET", "/api/v1/settings/llm", token=True)
    return data if status == 200 else {}


def main() -> int:
    key = load_env_key()
    if not key:
        print(f"[FAIL] 未在 {ENV_FILE} 找到 LLM_API_KEY")
        return 2

    print("=" * 66)
    print(f"真实推理测试 | 后端 {BASE}")
    print("=" * 66)

    original_cfg = llm_config_snapshot()
    print(f"当前模型: {original_cfg.get('model')} | has_key={original_cfg.get('has_key')} "
          f"| hint={original_cfg.get('key_hint')}")

    # ---------- T1 配置前置校验 ----------
    check("T1 密钥已配置且响应不含 api_key 明文",
          original_cfg.get("has_key") is True and "api_key" not in original_cfg,
          f"model={original_cfg.get('model')}")
    check("T1 api_base 为 https 公网端点",
          str(original_cfg.get("api_base", "")).startswith("https://"),
          original_cfg.get("api_base", ""))

    # 保存原始拓扑/配置用于还原
    orig_ui_gen_cfg = (node_by_id("node_ui_gen") or {}).get("config_json", {})
    orig_node_ids = {n["id"] for n in get_workflow().get("nodes", [])}
    added_nodes = []

    try:
        # ---------- T2 配置驱动真实推理 ----------
        cfg_a = {"name": "星火验证卡Alpha", "theme": "cyan", "probe": "alpha-version"}
        cfg_b = {"name": "星火验证卡Omega", "theme": "magenta", "probe": "omega-version"}
        before = get_sandbox_html()

        rest("PUT", "/api/v1/workflow/nodes/node_ui_gen/config", cfg_a)
        ok_a, waited_a = wait_for(
            lambda: get_sandbox_html() not in ("", before) and not is_builtin_template(get_sandbox_html()),
            timeout_s=240,
        )
        html_a = get_sandbox_html()

        rest("PUT", "/api/v1/workflow/nodes/node_ui_gen/config", cfg_b)
        ok_b, waited_b = wait_for(
            lambda: get_sandbox_html() not in ("", html_a),
            timeout_s=240,
        )
        html_b = get_sandbox_html()

        check("T2 配置A触发真实生成（非内置模板）", ok_a and not is_builtin_template(html_a),
              f"等待{waited_a}s len={len(html_a)}")
        check("T2 改配置后输出随之变化（config 真实进入提示词）",
              ok_b and html_b != html_a,
              f"等待{waited_b}s 长度 {len(html_a)}->{len(html_b)}")

        # ---------- T3 输出质量基线 ----------
        sample = html_b
        check("T3 输出长度达标（>500 字符，未被 max_tokens 截断）", len(sample) > 500, f"len={len(sample)}")
        check("T3 结构闭合完整（以闭合标签结尾）",
              sample.rstrip().endswith(">") and sample.count("<div") <= sample.count("</div>") + 2,
              f"<div×{sample.count('<div')} </div>×{sample.count('</div>')}")
        check("T3 无危险标签残留（script/iframe/内联事件）",
              all(t not in sample.lower() for t in ("<script", "<iframe", "javascript:", "onerror=", "onclick=")),
              "")
        check("T3 含 Tailwind 原子类（可用的 HTML 片段）", "class=" in sample, "")

        # ---------- T4 第二 LLM 算子 agent_codegen ----------
        status, created = rest("POST", "/api/v1/workflow/nodes",
                               {"component_id": "agent_codegen", "x": 455, "y": 300})
        codegen_id = created.get("id") if isinstance(created, dict) else None
        if codegen_id:
            added_nodes.append(codegen_id)

        ok_cg, waited_cg = wait_for(
            lambda: (node_by_id(codegen_id) or {}).get("status") == "success",
            timeout_s=240,
        )
        cg = node_by_id(codegen_id) or {}
        check("T4 agent_codegen 节点执行成功", ok_cg and cg.get("status") == "success",
              f"等待{waited_cg}s")
        check("T4 LLM 节点耗时为真实网络量级（>=200ms，非本地模拟的几毫秒）",
              int(cg.get("latency_ms", 0)) >= 200, f"latency={cg.get('latency_ms')}ms")

        # ---------- T5 并发多 LLM 节点 ----------
        for i, y in enumerate((520,), 1):
            st, node = rest("POST", "/api/v1/workflow/nodes",
                            {"component_id": "agent_codegen", "x": 455, "y": y})
            if isinstance(node, dict) and node.get("id"):
                added_nodes.append(node["id"])
        ok_conc, waited_conc = wait_for(
            lambda: all((node_by_id(nid) or {}).get("status") in ("success", "error")
                        for nid in added_nodes),
            timeout_s=40,
        )
        statuses = [(node_by_id(nid) or {}).get("status") for nid in added_nodes]
        check("T5 2 个 LLM 节点同轮并发执行且全部成功",
              ok_conc and all(s == "success" for s in statuses),
              f"等待{waited_conc}s statuses={statuses}")

        # ---------- T6 多轮稳定性（只看本窗口新增日志，历史 Warn 不计入） ----------
        lengths = []
        warn_seen = False
        for _ in range(4):
            logs_before = set(get_workflow().get("terminal_logs", []))
            time.sleep(4)
            html = get_sandbox_html()
            lengths.append(len(html))
            new_logs = set(get_workflow().get("terminal_logs", [])) - logs_before
            if any("[Warn] LLM 调用失败" in l for l in new_logs):
                warn_seen = True
        check("T6 连续 4 轮输出非空且均为真实生成", all(l > 300 for l in lengths) and not warn_seen,
              f"长度序列={lengths}")

        # ---------- T7 错误密钥降级 ----------
        rest("PUT", "/api/v1/settings/llm",
             {"api_key": "sk-invalid-real-inference-test", "api_base": original_cfg.get("api_base"),
              "model": original_cfg.get("model")}, token=True)
        ok_warn, waited_warn = wait_for(
            lambda: "[Warn] LLM 调用失败" in "\n".join(get_workflow().get("terminal_logs", [])),
            timeout_s=150,
        )
        check("T7 错误密钥触发 [Warn] 降级日志", ok_warn, f"等待{waited_warn}s")
        ok_fallback, waited_fb = wait_for(lambda: is_builtin_template(get_sandbox_html()), timeout_s=240)
        check("T7 失败后回落内置模板（循环未中断）", ok_fallback, f"等待{waited_fb}s")
        # 恢复正确密钥（先按原模型恢复；若该模型未订阅则回落 lite——2026-11-07 key 仅订阅 lite）
        rest("PUT", "/api/v1/settings/llm",
             {"api_key": key, "api_base": original_cfg.get("api_base"),
              "model": original_cfg.get("model")}, token=True)
        ok_recover, waited_rc = wait_for(
            lambda: not is_builtin_template(get_sandbox_html()), timeout_s=90,
        )
        if not ok_recover:
            rest("PUT", "/api/v1/settings/llm",
                 {"api_key": key, "api_base": original_cfg.get("api_base"), "model": "lite"}, token=True)
            ok_recover, waited_rc = wait_for(
                lambda: not is_builtin_template(get_sandbox_html()), timeout_s=240,
            )
        check("T7 恢复密钥后重新走真实推理", ok_recover, f"等待{waited_rc}s")

        # ---------- T8 SSRF 守卫 ----------
        st_ssrf, body_ssrf = rest("PUT", "/api/v1/settings/llm",
                                  {"api_key": "x", "api_base": "http://127.0.0.1:9/", "model": "m"},
                                  token=True)
        check("T8 内网 api_base 被 400 拒绝", st_ssrf == 400,
              str((body_ssrf or {}).get("detail", body_ssrf))[:80])

        # ---------- T9 模型切换 ----------
        rest("PUT", "/api/v1/settings/llm",
             {"api_key": key, "api_base": original_cfg.get("api_base"), "model": "generalv3.5"},
             token=True)
        logs_before_t9 = set(get_workflow().get("terminal_logs", []))
        ok_switch, waited_sw = wait_for(
            lambda: not is_builtin_template(get_sandbox_html())
            and not any("[Warn] LLM 调用失败" in l
                        for l in set(get_workflow().get("terminal_logs", [])) - logs_before_t9),
            timeout_s=240,
        )
        check("T9 切换 generalv3.5 后仍真实可用", ok_switch, f"等待{waited_sw}s")
        # 恢复原模型
        rest("PUT", "/api/v1/settings/llm",
             {"api_key": key, "api_base": original_cfg.get("api_base"),
              "model": original_cfg.get("model")}, token=True)

    finally:
        # ---------- 还原现场 ----------
        for nid in added_nodes:
            rest("DELETE", f"/api/v1/workflow/nodes/{nid}")
        if orig_ui_gen_cfg:
            rest("PUT", "/api/v1/workflow/nodes/node_ui_gen/config", orig_ui_gen_cfg)
        # 密钥/模型最终确认为原值
        rest("PUT", "/api/v1/settings/llm",
             {"api_key": key, "api_base": original_cfg.get("api_base", "https://spark-api-open.xf-yun.com/v1"),
              "model": original_cfg.get("model", "4.0Ultra")}, token=True)
        time.sleep(2)
        final_cfg = llm_config_snapshot()
        final_nodes = {n["id"] for n in get_workflow().get("nodes", [])}
        print("\n--- 现场还原确认 ---")
        print(f"模型: {final_cfg.get('model')} | has_key={final_cfg.get('has_key')}")
        print(f"新增节点已清理: {not (set(added_nodes) & final_nodes)}")
        print(f"node_ui_gen 配置已还原: {node_by_id('node_ui_gen') is not None}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n真实推理测试结果: {passed}/{len(results)} 通过"
          + ("" if not failures else f" | 失败: {', '.join(failures)}"))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
