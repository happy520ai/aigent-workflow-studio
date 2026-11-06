# tests/conftest.py —— 会话级 TestClient：整个测试会话共用一次 lifespan（真实后台引擎循环）
# 测试隔离：必须先于任何业务模块导入设置（拓扑持久化关闭 + 断点库指向临时目录）
import os
import tempfile

os.environ.setdefault("AIGENT_PERSIST_TOPOLOGY", "0")
os.environ.setdefault("AIGENT_DB_PATH", os.path.join(tempfile.mkdtemp(), "ckpt.db"))

import time

import pytest
from starlette.testclient import TestClient

from main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        # 等待遥测历史队列填满（CPU/内存 16 点、ECG 20 点），消除集成测试时序抖动
        deadline = time.time() + 8
        while time.time() < deadline:
            snap = c.get("/api/v1/workflow").json()
            if (
                len(snap["telemetry"]["cpu_history"]) >= 16
                and len(snap["telemetry"]["ecg_waveform"]) >= 20
            ):
                break
            time.sleep(0.2)
        yield c


@pytest.fixture(scope="session")
def perfect_client():
    """会话级 perfect_main 客户端（与 test_perfect_api.py 模块级同名 fixture 不冲突，
    该文件自带的 module 级 fixture 优先被使用）"""
    from perfect_main import app as perfect_app

    with TestClient(perfect_app) as c:
        deadline = time.time() + 8
        while time.time() < deadline:
            snap = c.get("/api/v1/workflow").json()
            if (
                len(snap["telemetry"]["cpu_history"]) >= 16
                and len(snap["telemetry"]["ecg_waveform"]) >= 20
            ):
                break
            time.sleep(0.2)
        yield c
