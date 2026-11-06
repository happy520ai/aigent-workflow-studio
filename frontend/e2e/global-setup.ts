// T51：E2E 全局准备——删除上一轮残留的持久化库（AIGENT_PERSIST_TOPOLOGY=1 时拓扑/断点跨轮累积）
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

export default function globalSetup(): void {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const db = path.join(here, '..', '..', 'backend', '_e2e_ckpt.db');
  for (const f of [db, `${db}-wal`, `${db}-shm`]) {
    try {
      fs.rmSync(f, { force: true });
    } catch {
      // 不存在则忽略
    }
  }
}
