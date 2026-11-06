# backend/conftest.py —— pytest 导入路径垫片 + 跨解释器 subprocess 引导
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"

# 若由非 venv 解释器启动（例如系统 python / 质量矩阵运行器），改用 backend/.venv
# 子进程重新执行 pytest 并透传退出码（Windows 上 os.execv 不会等待/回传退出码，
# 所以这里必须用 subprocess 阻塞等待），保证依赖版本与 requirements.txt 完全一致。
if (
    VENV_PYTHON.exists()
    and Path(sys.executable).resolve() != VENV_PYTHON.resolve()
    and os.environ.get("BACKEND_PYTEST_VENV") != "1"
):
    os.environ["BACKEND_PYTEST_VENV"] = "1"
    proc = subprocess.run(
        [str(VENV_PYTHON), "-m", "pytest", *sys.argv[1:]],
        cwd=str(BACKEND_DIR),
    )
    sys.exit(proc.returncode)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
