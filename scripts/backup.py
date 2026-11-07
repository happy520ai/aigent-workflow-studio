# scripts/backup.py —— T64：SQLite online backup（不阻塞业务，保留最近 N 份）
# 用法：backend/.venv/Scripts/python scripts/backup.py [--db PATH] [--out DIR] [--keep N]
# 默认：db = AIGENT_DB_PATH 或 backend/aigent_checkpoints.db；out = backend/backups；keep = 7
import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


def main() -> int:
    parser = argparse.ArgumentParser(description="AIGENT SQLite 在线备份")
    parser.add_argument("--db", default=None, help="源库路径（默认 AIGENT_DB_PATH 或 backend/aigent_checkpoints.db）")
    parser.add_argument("--out", default=None, help="备份目录（默认 backend/backups）")
    parser.add_argument("--keep", type=int, default=7, help="保留最近 N 份（默认 7）")
    args = parser.parse_args()

    src = Path(args.db or os.getenv("AIGENT_DB_PATH") or BACKEND_DIR / "aigent_checkpoints.db")
    if not src.exists():
        print(f"[backup] 源库不存在: {src}")
        return 1
    out_dir = Path(args.out or BACKEND_DIR / "backups")
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S%f")
    dest = out_dir / f"aigent-{stamp}.db"

    # SQLite online backup API：源与目标各自持连接，逐页拷贝，业务写入不被阻塞
    src_conn = sqlite3.connect(str(src))
    dest_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dest_conn)
        dest_conn.commit()
    finally:
        dest_conn.close()
        src_conn.close()

    # 剪枝：只保留最近 keep 份
    backups = sorted(out_dir.glob("aigent-*.db"))
    removed = 0
    for old in backups[: max(0, len(backups) - args.keep)]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass

    print(f"[backup] {src} -> {dest}")
    print(f"[backup] 共 {len(backups)} 份，剪枝 {removed} 份（保留最近 {args.keep}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
