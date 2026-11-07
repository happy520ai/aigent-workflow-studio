# backend/publisher.py
import io
import json
import zipfile
from datetime import datetime
from typing import Any


class WorkflowArtifactPublisher:
    """将智能体工作流生成的 UI 代码与神经元状态打包为可独立运行的 React 工程 ZIP"""

    @staticmethod
    def build_project_zip(
        sandbox_html: str,
        workflow_snapshot: dict[str, Any],
        shared_memory_bus: dict[str, Any],
    ) -> bytes:
        buffer = io.BytesIO()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. 写入生成的独立运行 HTML 预览入口
            standalone_html = f"""<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8" />
  <title>AIGENT Published App ({timestamp})</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-[#070a12] text-slate-100 min-h-screen flex items-center justify-center p-8">
  <div class="max-w-xl w-full space-y-4">
    {sandbox_html}
  </div>
</body>
</html>"""
            zf.writestr("dist/index.html", standalone_html)

            # 2. 写入 React 组件源码文件
            react_component_code = f"""import React from 'react';

export default function GeneratedAgentWidget() {{
  return (
    <div dangerouslySetInnerHTML={{{{ __html: {json.dumps(sandbox_html, ensure_ascii=False)} }}}} />
  );
}}
"""
            zf.writestr("src/GeneratedAgentWidget.tsx", react_component_code)

            # 3. 写入工作流完整 DAG 拓扑快照与共享记忆总线快照
            zf.writestr(
                "workflow-topology.v2.8.json",
                json.dumps(workflow_snapshot, indent=2, ensure_ascii=False),
            )
            zf.writestr(
                "neural-memory-bus.json",
                json.dumps(shared_memory_bus, indent=2, ensure_ascii=False),
            )

        buffer.seek(0)
        return buffer.getvalue()
