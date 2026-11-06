// frontend/src/hooks/useWorkflowApi.ts —— T40：REST 封装（统一 adminHeaders 与可读错误）
// 行为迁移自 Workbench 内联 fetch：调用方负责状态更新与日志，本层只负责「说人话」的失败。
import { API_BASE, adminHeaders } from '../config';
import type { NeuralEdge, RunRecord, WorkflowNode } from '../types';

async function parseErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const err = await res.json();
    return err.detail ?? `${fallback}: HTTP ${res.status}`;
  } catch {
    return `${fallback}: HTTP ${res.status}`;
  }
}

async function jsonOrThrow<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await parseErrorDetail(res, fallback));
  return res.json();
}

export const workflowApi = {
  getSnapshot: async (): Promise<any> => {
    const res = await fetch(`${API_BASE}/workflow`, { headers: adminHeaders() });
    return jsonOrThrow(res, '读取快照失败');
  },

  control: async (action: 'run' | 'pause' | 'debug' | 'reset'): Promise<void> => {
    await fetch(`${API_BASE}/workflow/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...adminHeaders() },
      body: JSON.stringify({ action }),
    });
  },

  addNode: async (payload: {
    component_id: string;
    x: number;
    y: number;
    connect_from: string | null;
  }): Promise<WorkflowNode> => {
    const res = await fetch(`${API_BASE}/workflow/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...adminHeaders() },
      body: JSON.stringify(payload),
    });
    return jsonOrThrow(res, '添加节点失败');
  },

  deleteNode: async (nodeId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/workflow/nodes/${nodeId}`, {
      method: 'DELETE',
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`删除节点失败: HTTP ${res.status}`);
  },

  deleteEdge: async (edgeId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/workflow/edges/${edgeId}`, {
      method: 'DELETE',
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`断开连线失败: HTTP ${res.status}`);
  },

  putNodeConfig: async (nodeId: string, config: Record<string, any>): Promise<WorkflowNode> => {
    const res = await fetch(`${API_BASE}/workflow/nodes/${nodeId}/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...adminHeaders() },
      body: JSON.stringify(config),
    });
    return jsonOrThrow(res, '热更新失败');
  },

  fetchRunHistory: async (): Promise<RunRecord[]> => {
    const res = await fetch(`${API_BASE}/runs?limit=5`, { headers: adminHeaders() });
    return jsonOrThrow(res, '读取运行记录失败');
  },

  fetchLlmSettings: async (): Promise<any> => {
    const res = await fetch(`${API_BASE}/settings/llm`, { headers: adminHeaders() });
    return jsonOrThrow(res, '读取失败');
  },

  updateLlmSettings: async (payload: {
    api_key: string;
    api_base: string;
    model: string;
  }): Promise<void> => {
    const res = await fetch(`${API_BASE}/settings/llm`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...adminHeaders() },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await parseErrorDetail(res, '更新模型配置失败'));
  },

  listWorkflows: async (): Promise<{ id: string; name: string; updated_at?: string }[]> => {
    const res = await fetch(`${API_BASE}/workflows`, { headers: adminHeaders() });
    return jsonOrThrow(res, '读取工作流列表失败');
  },

  createWorkflow: async (name: string): Promise<{ id: string; name: string }> => {
    const res = await fetch(`${API_BASE}/workflows`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...adminHeaders() },
      body: JSON.stringify({ name }),
    });
    return jsonOrThrow(res, '新建工作流失败');
  },

  activateWorkflow: async (id: string): Promise<any> => {
    const res = await fetch(`${API_BASE}/workflows/${encodeURIComponent(id)}/activate`, {
      method: 'POST',
      headers: adminHeaders(),
    });
    return jsonOrThrow(res, `切换工作流 ${id} 失败`);
  },

  batchPositions: async (
    positions: { id: string; x: number; y: number }[]
  ): Promise<{ updated: number; skipped: number }> => {
    const res = await fetch(`${API_BASE}/workflow/positions`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...adminHeaders() },
      body: JSON.stringify({ positions }),
    });
    return jsonOrThrow(res, '自动布局失败');
  },

  aiSuggest: async (prompt: string): Promise<{ added_nodes: number; added_edges: number }> => {
    const res = await fetch(`${API_BASE}/workflow/ai-suggest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...adminHeaders() },
      body: JSON.stringify({ prompt }),
    });
    return jsonOrThrow(res, 'AI 建议被拒绝');
  },
};

export type { WorkflowNode, NeuralEdge };
