// frontend/src/components/NodeCard.tsx —— T40：画布神经元节点卡片（原样迁出）
import React from 'react';
import { PhosphorECGWidget, AuraAICoreWidget, WireframeScannerWidget } from './NodeMicroWidgets';
import type { WorkflowNode } from '../types';

export const NodeCard: React.FC<{
  node: WorkflowNode;
  isSelected: boolean;
  isInSelection?: boolean;
  isLinkSource: boolean;
  isRunning: boolean;
  ecgSeries: number[];
  onNodeMouseDown: (e: React.MouseEvent<HTMLDivElement>, node: WorkflowNode) => void;
  onOpenSandbox: () => void;
}> = ({ node, isSelected, isInSelection, isLinkSource, isRunning, ecgSeries, onNodeMouseDown, onOpenSandbox }) => {
  // 状态着色边框：error 红 / skipped 灰 / 其余主题色
  const borderColor =
    node.status === 'error'
      ? '#f43f5e'
      : node.status === 'skipped'
      ? '#64748b'
      : isLinkSource
      ? '#00f5d4'
      : node.theme_color;
  return (
    <div
      title={node.status === 'error' && node.last_error ? node.last_error : undefined}
      onMouseDown={(e) => onNodeMouseDown(e, node)}
      style={{
        left: `${node.position.x}px`,
        top: `${node.position.y}px`,
        borderColor,
        boxShadow: isSelected
          ? `0 0 24px ${node.theme_color}85, inset 0 0 14px ${node.theme_color}35`
          : `0 0 15px ${node.theme_color}45, inset 0 0 8px ${node.theme_color}20`,
      }}
      className={`absolute w-[195px] rounded-xl bg-[#0e1628]/80 backdrop-blur-md border p-3 cursor-grab active:cursor-grabbing z-20 transition-shadow ${
        isInSelection ? 'ring-2 ring-cyan-400/80 border-dashed' : ''
      }`}
    >
      <div className="flex items-start justify-between mb-1.5">
        <div>
          <div className="text-xs font-bold text-white flex items-center space-x-1.5">
            <span
              className="w-2 h-2 rounded-full inline-block shadow-[0_0_8px_currentColor]"
              style={{ backgroundColor: node.theme_color, color: node.theme_color }}
            />
            <span>{node.title}</span>
          </div>
          <div className="text-[10px] text-slate-400 pl-3.5">{node.subtitle}</div>
        </div>

        {node.status === 'error' ? (
          <span className="px-1.5 py-0.5 text-[9px] rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 font-mono">
            Error
          </span>
        ) : node.degraded ? (
          // T24：LLM 降级徽章（后端 node.degraded 置位时可见）
          <span
            className="px-1.5 py-0.5 text-[9px] rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono"
            title="LLM 调用失败，已降级为内置模板"
          >
            降级
          </span>
        ) : node.type === 'dom_renderer' ? (
          <span className="px-1.5 py-0.5 text-[9px] rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono">
            Success
          </span>
        ) : (
          <span
            className="w-2.5 h-2.5 rounded-full animate-ping"
            style={{ backgroundColor: node.theme_color }}
          />
        )}
      </div>

      {/* 挂载 60FPS 节点内部微动效 */}
      {node.type === 'event_capturer' && (
        <PhosphorECGWidget isRunning={isRunning} waveform={ecgSeries} />
      )}

      {node.type === 'intent_agent' && <AuraAICoreWidget isRunning={isRunning} />}

      {node.type === 'ui_generation' && (
        <WireframeScannerWidget progress={node.progress} isRunning={isRunning} />
      )}

      {node.type === 'dom_renderer' && (
        <div className="mt-2 space-y-1.5">
          <div className="grid grid-cols-2 gap-1.5">
            <div className="h-11 rounded bg-slate-950 border border-slate-800 p-1 font-mono text-[7px] text-emerald-400 leading-tight overflow-hidden">
              <div>&lt;div class=&quot;ui&quot;&gt;</div>
              <div className="pl-1 text-cyan-400">&lt;Agent /&gt;</div>
              <div>&lt;/div&gt;</div>
            </div>
            <div
              onClick={(e) => {
                e.stopPropagation();
                onOpenSandbox();
              }}
              className="h-11 rounded bg-white p-1 flex flex-col justify-between cursor-pointer hover:ring-2 hover:ring-cyan-400"
            >
              <div className="w-1/2 h-1.5 bg-blue-600 rounded-sm" />
              <div className="w-full h-4 bg-slate-200 rounded-sm flex items-center justify-center text-[8px] text-slate-700 font-bold">
                预览沙盒
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 真实遥测小字：延迟 · 置信度（随 node_update 实时变化） */}
      <div className="mt-2 pt-1.5 border-t border-slate-800/80 text-[9px] font-mono text-slate-400 flex items-center justify-between">
        <span>
          {node.latency_ms}ms · {node.confidence}%
        </span>
        <span className={node.status === 'skipped' ? 'text-slate-500' : ''}>{node.status}</span>
      </div>
    </div>
  );
};
