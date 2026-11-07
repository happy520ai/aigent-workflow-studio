# 恢复指南（T64）—— AIGENT-WORKFLOW STUDIO

## 什么时候需要恢复

- SQLite 库损坏 / 误删（`backend/aigent_checkpoints.db` 或 compose 命名卷 `aigent-data` 内同名文件）
- 升级回滚需要回到旧数据状态

## 前置：停止写入

```bash
docker compose stop aigent-backend      # compose 部署
# 或本机部署：停止 uvicorn 进程
```

## 备份从哪来

- 定时/手动备份：`backend/.venv/Scripts/python scripts/backup.py --keep 7`
  - 输出到 `backend/backups/aigent-<时间戳>.db`（SQLite online backup，业务不中断）
  - compose 部署时：`--db` 指向卷内文件。先取出来：
    `docker compose cp aigent-backend:/app/data/aigent_checkpoints.db ./volume-copy.db`

## 恢复步骤

1. 停止后端（见上）。
2. 将损坏/目标库移走留证（不要直接覆盖）：
   ```bash
   mv backend/aigent_checkpoints.db backend/aigent_checkpoints.db.corrupt
   # 同时移走可能的 WAL 伴生文件
   rm -f backend/aigent_checkpoints.db-wal backend/aigent_checkpoints.db-shm
   ```
3. 拷贝备份为库名：
   ```bash
   cp backend/backups/aigent-<时间戳>.db backend/aigent_checkpoints.db
   ```
4. 重启后端并验证：
   ```bash
   docker compose start aigent-backend   # 或本机启动 uvicorn
   curl http://127.0.0.1:8000/readyz     # {"status":"ready",...}
   curl http://127.0.0.1:8000/api/v1/checkpoints?limit=5
   ```
5. 校验断点数量与备份时一致（本文件底部记录了最近一次实测）。

## 回滚备份（恢复失败时）

```bash
mv backend/aigent_checkpoints.db.corrupt backend/aigent_checkpoints.db
```

## 最近一次实测（2026-11-07）

见 git 历史 T64 提交：备份 → 清库 → 恢复 → 断点数一致（3/3），脚本输出与
`readyz=ready` 均已核验。
