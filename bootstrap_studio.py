# bootstrap_studio.py
import os
import sqlite3
from pathlib import Path

REQUIRED_DIRS = [
    "backend",
    "backend/data",
    "frontend",
    "frontend/src",
    "frontend/src/components",
    "frontend/src/hooks",
]

REQUIRED_FILES = [
    "docker-compose.yml",
    "start.sh",
    "backend/Dockerfile",
    "backend/requirements.txt",
    "backend/models.py",
    "backend/operator_registry.py",
    "backend/ast_validator.py",
    "backend/publisher.py",
    "backend/perfect_engine.py",
    "backend/perfect_main.py",
    "backend/test_workflow_e2e.py",
    "frontend/Dockerfile",
    "frontend/nginx.conf",
    "frontend/package.json",
    "frontend/vite.config.ts",
    "frontend/tsconfig.json",
    "frontend/tailwind.config.js",
    "frontend/postcss.config.js",
    "frontend/index.html",
    "frontend/src/main.tsx",
    "frontend/src/index.css",
    "frontend/src/Workbench.tsx",
    "frontend/src/components/NeuralBioCanvas.tsx",
    "frontend/src/components/SandboxAndTimeTravel.tsx",
    "frontend/src/hooks/useWorkflowBackend.ts",
    "frontend/src/hooks/useSynapseLinker.ts",
]


def bootstrap_workspace() -> None:
    root = Path(__file__).parent.resolve()
    print(f"⚡ 正在初始化 AIGENT-WORKFLOW STUDIO v2.8 工程目录: {root}")

    for d in REQUIRED_DIRS:
        dir_path = root / d
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"  [DIR]  已就绪: {d}/")

    # 预初始化 SQLite 时间旅行断点数据库表（含 topology_json 拓扑快照列与 topology 单行表）
    db_file = root / "backend" / "aigent_checkpoints.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                state_payload TEXT NOT NULL,
                generated_code TEXT NOT NULL
            )
            """
        )
        # 旧库无损迁移：补 topology_json 列
        existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(checkpoints)").fetchall()]
        if "topology_json" not in existing_cols:
            conn.execute("ALTER TABLE checkpoints ADD COLUMN topology_json TEXT DEFAULT ''")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topology (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                nodes_json TEXT NOT NULL,
                edges_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    print(f"  [DB]   SQLite 时间旅行持久化库已就绪: {db_file.name}")

    missing = [f for f in REQUIRED_FILES if not (root / f).exists()]
    if missing:
        print("\n📋 待落盘源码文件清单:")
        for m in missing:
            print(f"  - {m}")
    else:
        print("\n✅ 全部 26 个前后端源码与容器编排文件均已完整就位！")


if __name__ == "__main__":
    bootstrap_workspace()
