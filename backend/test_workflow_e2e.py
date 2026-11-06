# backend/test_workflow_e2e.py
import asyncio
import unittest
from fastapi.testclient import TestClient

from ast_validator import FrontendASTValidator
from perfect_main import app, engine


class TestAigentWorkflowStudio(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_01_topological_kahn_compiler(self) -> None:
        """验证 5 大核心神经元节点被编译为 3 层并发 DAG 拓扑结构"""
        layers = engine.compile_topological_layers()
        self.assertEqual(layers[0], ["node_event_capturer"])
        self.assertEqual(layers[1], ["node_intent_agent"])
        self.assertEqual(
            set(layers[2]),
            {"node_ui_gen", "node_co_agent", "node_dom_renderer"},
        )

    def test_02_ast_validator_and_auto_healing(self) -> None:
        """验证 AST 引擎自动剥离恶意 <script> 并自动补全未闭合的 <div><span> 标签"""
        broken_code = """
        <div className="p-4 bg-slate-900">
          <script>alert('xss')</script>
          <span class="text-cyan-400">UI Generation Agent
        """
        report = FrontendASTValidator.validate_and_heal(broken_code)
        self.assertNotIn("<script>", report.healed_code)
        self.assertIn("class=", report.healed_code)
        self.assertTrue(report.healed_code.endswith("</span></div>"))
        self.assertEqual(report.security_score, 75.0)

    def test_03_rest_workflow_and_control_lifecycle(self) -> None:
        """验证运行、暂停、调试指令及节点 JSON 配置热更新"""
        res = self.client.get("/api/v1/workflow")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["version"], "v2.8")
        self.assertEqual(len(data["nodes"]), 5)

        # 暂停工作流
        pause_res = self.client.post("/api/v1/workflow/control", json={"action": "pause"})
        self.assertEqual(pause_res.json()["project_status"], "已暂停")

        # 恢复运行
        run_res = self.client.post("/api/v1/workflow/control", json={"action": "run"})
        self.assertEqual(run_res.json()["project_status"], "运行中")

    def test_04_sqlite_checkpoint_persistence(self) -> None:
        """验证 SQLite 时间旅行断点写入与读取"""
        ckpt_id = asyncio.run(
            engine.checkpoint_store.save_checkpoint(
                run_id="test_run_01",
                node_id="node_ui_gen",
                state_payload={"confidence": 98.6},
                generated_code="<div>Test UI</div>",
            )
        )
        records = asyncio.run(engine.checkpoint_store.list_checkpoints(limit=5))
        self.assertTrue(any(r["checkpoint_id"] == ckpt_id for r in records))


if __name__ == "__main__":
    unittest.main(verbosity=2)
