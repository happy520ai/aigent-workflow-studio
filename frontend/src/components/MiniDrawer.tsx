// frontend/src/components/MiniDrawer.tsx —— T40：迷你抽屉浮层（共享记忆总线 / 拓扑与运行记录 / 大模型设置，原样迁出）
import React from 'react';
import { X, Trash2, Unplug, RefreshCw } from 'lucide-react';
import type { NeuralEdge, RunRecord, WorkflowNode } from '../types';

export type MiniDrawerKind = 'none' | 'memory' | 'topology' | 'settings';

export const MiniDrawer: React.FC<{
  kind: MiniDrawerKind;
  onClose: () => void;
  wsConnected: boolean;
  sharedMemoryBus: Record<string, any>;
  nodes: WorkflowNode[];
  edges: NeuralEdge[];
  runHistory: RunRecord[];
  onDeleteNode: (id: string) => void;
  onDeleteEdge: (id: string) => void;
  onRefreshRunHistory: () => void;
  llmForm: { api_key: string; api_base: string; model: string; key_hint: string };
  onLlmFormChange: (patch: Partial<{ api_key: string; api_base: string; model: string }>) => void;
  llmMsg: string;
  adminToken: string;
  onAdminTokenChange: (v: string) => void;
  onSaveLlm: () => void;
}> = ({
  kind,
  onClose,
  wsConnected,
  sharedMemoryBus,
  nodes,
  edges,
  runHistory,
  onDeleteNode,
  onDeleteEdge,
  onRefreshRunHistory,
  llmForm,
  onLlmFormChange,
  llmMsg,
  adminToken,
  onAdminTokenChange,
  onSaveLlm,
}) => {
  if (kind === 'none') return null;
  return (
    <div className="absolute left-12 top-0 bottom-0 w-[280px] bg-[#0d1322]/97 border-r border-slate-800/80 backdrop-blur-md z-40 flex flex-col p-3 space-y-3 overflow-y-auto">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-200">
          {kind === 'memory' && '共享记忆总线 (Memory Bus)'}
          {kind === 'topology' && '拓扑与运行记录 (Topology)'}
          {kind === 'settings' && '大模型设置 (LLM Settings)'}
        </span>
        <button
          onClick={onClose}
          className="p-1 rounded bg-slate-800/80 text-slate-400 hover:text-white"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* —— 共享记忆总线 —— */}
      {kind === 'memory' && (
        <pre className="flex-1 bg-[#080c16] border border-slate-800 rounded-lg p-2.5 font-mono text-[10px] text-cyan-300 whitespace-pre-wrap break-words overflow-y-auto leading-relaxed">
          {JSON.stringify(sharedMemoryBus, null, 2)}
        </pre>
      )}

      {/* —— 拓扑与运行记录 —— */}
      {kind === 'topology' &&
        (wsConnected ? (
          <div className="flex-1 flex flex-col space-y-3">
            <div>
              <div className="text-[11px] text-slate-400 mb-1.5">节点 ({nodes.length})</div>
              <div className="space-y-1">
                {nodes.map((n) => (
                  <div
                    key={n.id}
                    className="flex items-center justify-between px-2 py-1 rounded bg-[#111a2e] border border-slate-800"
                  >
                    <div className="min-w-0">
                      <div className="text-[11px] text-slate-200 truncate">{n.title}</div>
                      <div className="text-[9px] font-mono text-slate-500 truncate">
                        {n.id} · {n.status} · {n.latency_ms}ms
                      </div>
                    </div>
                    <button
                      onClick={() => onDeleteNode(n.id)}
                      className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/40"
                      title="删除节点"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="text-[11px] text-slate-400 mb-1.5">连线 ({edges.length})</div>
              <div className="space-y-1">
                {edges.map((e) => (
                  <div
                    key={e.id}
                    className="flex items-center justify-between px-2 py-1 rounded bg-[#111a2e] border border-slate-800"
                  >
                    <span className="text-[10px] font-mono text-slate-300 truncate">
                      {e.source} → {e.target}
                    </span>
                    <button
                      onClick={() => onDeleteEdge(e.id)}
                      className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/40"
                      title="断开连线"
                    >
                      <Unplug className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex-1 min-h-0 flex flex-col">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] text-slate-400">最近运行</span>
                <button
                  onClick={onRefreshRunHistory}
                  className="p-1 rounded text-slate-500 hover:text-cyan-300"
                  title="刷新运行记录"
                >
                  <RefreshCw className="w-3 h-3" />
                </button>
              </div>
              <div className="flex-1 space-y-1 overflow-y-auto">
                {runHistory.length === 0 && (
                  <div className="text-[10px] text-slate-500 font-mono">暂无运行记录</div>
                )}
                {runHistory.map((r) => (
                  <div
                    key={r.round_id}
                    className="px-2 py-1 rounded bg-[#080c16] border border-slate-800/80"
                  >
                    <div className="text-[10px] font-mono text-cyan-300">{r.round_id}</div>
                    <div className="text-[9px] font-mono text-slate-500 truncate">
                      {r.nodes.map((nd) => `${nd.id.split('_')[1]}:${nd.status}`).join(' | ')}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-[11px] text-slate-500">
            仅后端在线时可用
          </div>
        ))}

      {/* —— 大模型设置（T51：令牌填写恰是 WS 因无令牌被拒时的自救入口，故不依赖 wsConnected） —— */}
      {kind === 'settings' && (
        <div className="flex-1 flex flex-col space-y-2.5">
          <div className="text-[10px] font-mono text-slate-500 break-all">
            {llmMsg || '读取中...'}
          </div>
            <label className="text-[10px] text-slate-400">
              api_key（留空表示不修改 {llmForm.key_hint ? `| 当前 ${llmForm.key_hint}` : ''}）
              <input
                type="password"
                value={llmForm.api_key}
                onChange={(e) => onLlmFormChange({ api_key: e.target.value })}
                placeholder="sk-..."
                className="mt-1 w-full bg-[#090e1a] border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-cyan-500"
              />
            </label>
            <label className="text-[10px] text-slate-400">
              api_base
              <input
                type="text"
                value={llmForm.api_base}
                onChange={(e) => onLlmFormChange({ api_base: e.target.value })}
                className="mt-1 w-full bg-[#090e1a] border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-cyan-500"
              />
            </label>
            <label className="text-[10px] text-slate-400">
              model
              <input
                type="text"
                value={llmForm.model}
                onChange={(e) => onLlmFormChange({ model: e.target.value })}
                className="mt-1 w-full bg-[#090e1a] border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-cyan-500"
              />
            </label>
            <label className="text-[10px] text-slate-400">
              管理令牌（可选，仅存 sessionStorage）
              <input
                type="password"
                value={adminToken}
                onChange={(e) => onAdminTokenChange(e.target.value)}
                placeholder="AIGENT_ADMIN_TOKEN"
                className="mt-1 w-full bg-[#090e1a] border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-amber-500"
              />
            </label>
            <button
              onClick={onSaveLlm}
              className="w-full py-1.5 rounded-md bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 text-xs font-semibold hover:bg-cyan-500/30"
            >
              保存模型配置
            </button>
        </div>
      )}
    </div>
  );
};
