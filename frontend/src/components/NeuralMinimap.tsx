// frontend/src/components/NeuralMinimap.tsx
import React from 'react';

interface MiniNode {
  id: string;
  x: number;
  y: number;
  themeColor: string;
}

interface MiniEdge {
  id: string;
  source: string;
  target: string;
}

interface Props {
  nodes: MiniNode[];
  edges: MiniEdge[];
  selectedNodeId: string;
  zoom: number;
  pan: { x: number; y: number };
  onResetViewport: () => void;
  onSelectNode: (id: string) => void;
}

export const NeuralMinimap: React.FC<Props> = ({
  nodes,
  edges,
  selectedNodeId,
  zoom,
  onResetViewport,
  onSelectNode,
}) => {
  const scaleX = 0.16;
  const scaleY = 0.16;

  return (
    <div className="absolute right-4 bottom-4 w-[168px] h-[112px] rounded-xl bg-[#0b1120]/85 backdrop-blur-md border border-slate-700/80 shadow-[0_0_20px_rgba(0,0,0,0.65)] p-2 z-30 flex flex-col justify-between">
      <div className="flex items-center justify-between text-[9px] text-slate-400 font-mono border-b border-slate-800 pb-1">
        <span>NEURAL MINIMAP</span>
        <button
          onClick={onResetViewport}
          className="px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30"
          title="点击复位视口缩放"
        >
          {Math.round(zoom * 100)}%
        </button>
      </div>

      <svg className="w-full flex-1 overflow-visible">
        {edges.map((e) => {
          const s = nodes.find((n) => n.id === e.source);
          const t = nodes.find((n) => n.id === e.target);
          if (!s || !t) return null;
          return (
            <line
              key={e.id}
              x1={s.x * scaleX + 14}
              y1={s.y * scaleY + 8}
              x2={t.x * scaleX + 14}
              y2={t.y * scaleY + 8}
              stroke="#38bdf8"
              strokeWidth="1"
              strokeOpacity="0.6"
            />
          );
        })}

        {nodes.map((n) => {
          const isSel = n.id === selectedNodeId;
          return (
            <g
              key={n.id}
              onClick={() => onSelectNode(n.id)}
              className="cursor-pointer"
            >
              <rect
                x={n.x * scaleX}
                y={n.y * scaleY}
                width="26"
                height="14"
                rx="3"
                fill={isSel ? n.themeColor : '#1e293b'}
                stroke={n.themeColor}
                strokeWidth={isSel ? '1.5' : '0.8'}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
};
