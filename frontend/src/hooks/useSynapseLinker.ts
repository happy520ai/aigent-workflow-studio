// frontend/src/hooks/useSynapseLinker.ts
import { useState, useCallback } from 'react';
import { adminHeaders } from '../config';

export interface SynapseEdge {
  id: string;
  source: string;
  target: string;
  latency_ms: number;
  confidence_pct: number;
  connection_status: string;
  active_pulse: boolean;
}

export function useSynapseLinker(
  apiBase = 'http://localhost:8000/api/v1',
  onEdgeCreated?: (edge: SynapseEdge) => void,
  onError?: (msg: string) => void
) {
  const [linkingSourceId, setLinkingSourceId] = useState<string | null>(null);

  // 按住 Shift 点击节点：第一次选起点，第二次选终点并生成突触连线
  const handleNodeShiftClick = useCallback(
    async (nodeId: string) => {
      if (!linkingSourceId) {
        setLinkingSourceId(nodeId);
        return;
      }
      if (linkingSourceId === nodeId) {
        setLinkingSourceId(null);
        return;
      }

      const source = linkingSourceId;
      setLinkingSourceId(null);

      // 连线以后端结果为准：后端拒绝（自环/重复/成环/404）则不建线
      try {
        const res = await fetch(`${apiBase}/workflow/edges`, {
          method: 'POST',
          // T10/T43：突触连线创建同样携带管理令牌
          headers: { 'Content-Type': 'application/json', ...adminHeaders() },
          body: JSON.stringify({ source, target: nodeId }),
        });
        if (res.ok) {
          const created: SynapseEdge = await res.json();
          if (onEdgeCreated) {
            onEdgeCreated(created);
          }
        } else {
          // 后端 4xx：交给 Workbench 写错误日志
          let detail = '';
          try {
            const err = await res.json();
            detail = err.detail ?? JSON.stringify(err);
          } catch {
            detail = `HTTP ${res.status}`;
          }
          if (onError) {
            onError(detail);
          }
        }
      } catch {
        // 仅网络异常（离线）才退回本地生成边，本地仿真模式接管
        const localEdge: SynapseEdge = {
          id: `edge_${source}_${nodeId}_${Date.now().toString().slice(-3)}`,
          source,
          target: nodeId,
          latency_ms: 8,
          confidence_pct: 99.2,
          connection_status: '已连接',
          active_pulse: true,
        };
        if (onEdgeCreated) {
          onEdgeCreated(localEdge);
        }
      }
    },
    [linkingSourceId, apiBase, onEdgeCreated, onError]
  );

  // 节点拖拽结束时将最新坐标同步至后端拓扑图
  const persistNodePosition = useCallback(
    async (nodeId: string, x: number, y: number) => {
      try {
        await fetch(`${apiBase}/workflow/nodes/${nodeId}/position`, {
          // T10/T43：坐标持久化同样携带管理令牌
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', ...adminHeaders() },
          body: JSON.stringify({ x, y }),
        });
      } catch {
        // 本地模式下忽略
      }
    },
    [apiBase]
  );

  return {
    linkingSourceId,
    handleNodeShiftClick,
    persistNodePosition,
    cancelLinking: () => setLinkingSourceId(null),
  };
}
