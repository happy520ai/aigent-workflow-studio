#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  ⚡ 启动前端智能体工作流平台 (AIGENT-WORKFLOW STUDIO v2.8)"
echo "=========================================================="

if command -v docker &> /dev/null && docker compose version &> /dev/null; then
  echo "[1/2] 检测到 Docker 环境，正在构建并启动全栈容器集群..."
  docker compose up --build -d
  echo "[2/2] 部署完成！"
  echo "  -> 前端神经元工作台: http://localhost:3000"
  echo "  -> 后端 OpenAPI 文档: http://localhost:8000/docs"
else
  echo "[1/2] 未检测到 Docker，正在以本地开发进程启动前后端..."
  (cd backend && pip install -r requirements.txt && uvicorn perfect_main:app --host 0.0.0.0 --port 8000 &)
  (cd frontend && npm install && npm run dev)
fi
