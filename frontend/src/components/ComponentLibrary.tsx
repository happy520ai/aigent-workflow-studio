// frontend/src/components/ComponentLibrary.tsx —— T40：左侧算子组件库面板（原样迁出）
import React from 'react';
import {
  Zap,
  Clock,
  MessageSquare,
  Eye,
  Network,
  Code,
  ArrowLeftRight,
  Database,
  LayoutGrid,
  Terminal,
  FlaskConical,
  Rocket,
  Search,
  Filter,
  ChevronDown,
  Sparkles,
} from 'lucide-react';

export interface SidebarItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

export const SIDEBAR_GROUPS: { title: string; items: SidebarItem[] }[] = [
  {
    title: '触发器 (Triggers)',
    items: [
      { id: 'trig_events', label: '页面事件 (Events)', icon: Zap, color: '#10b981' },
      { id: 'trig_schedule', label: '定时触发 (Schedule)', icon: Clock, color: '#10b981' },
    ],
  },
  {
    title: '感知解析 (Perception)',
    items: [
      { id: 'perc_nlu', label: '自然语言理解 (NLU)', icon: MessageSquare, color: '#38bdf8' },
      { id: 'perc_vision', label: '视觉输入 (Vision)', icon: Eye, color: '#38bdf8' },
    ],
  },
  {
    title: 'AI 智能体 (Agents)',
    items: [
      { id: 'agent_intent', label: '意图分析 (Intent Agent)', icon: Network, color: '#6366f1' },
      { id: 'agent_codegen', label: '代码生成 (CodeGen)', icon: Code, color: '#6366f1' },
    ],
  },
  {
    title: '数据逻辑 (Logic)',
    items: [
      { id: 'logic_transform', label: '数据转换 (Transform)', icon: ArrowLeftRight, color: '#a855f7' },
      { id: 'logic_state', label: '状态管理 (State)', icon: Database, color: '#a855f7' },
    ],
  },
  {
    title: '前端渲染 (Frontend)',
    items: [
      { id: 'fe_assemble', label: '组件装配 (Assemble)', icon: LayoutGrid, color: '#38bdf8' },
      { id: 'fe_render', label: 'DOM 渲染 (Render)', icon: Terminal, color: '#38bdf8' },
    ],
  },
  {
    title: '部署 (Deploy)',
    items: [
      { id: 'dep_test', label: '沙盒测试 (Test)', icon: FlaskConical, color: '#ec4899' },
      { id: 'dep_publish', label: '发布 (Publish)', icon: Rocket, color: '#ec4899' },
    ],
  },
];

export const ComponentLibrary: React.FC<{
  search: string;
  onSearchChange: (v: string) => void;
  onAddItem: (item: SidebarItem) => void;
  onAiSuggest: () => void;
}> = ({ search, onSearchChange, onAddItem, onAiSuggest }) => (
  <aside className="w-[230px] bg-[#0d1322]/90 border-r border-slate-800/80 p-3 flex flex-col overflow-y-auto z-20">
    <div className="flex items-center space-x-1.5 mb-3">
      <div className="relative flex-1">
        <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="搜索库"
          className="w-full bg-[#151e32] border border-slate-700/70 rounded-md py-1 pl-7 pr-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400"
        />
      </div>
      <button className="p-1.5 bg-[#151e32] border border-slate-700/70 rounded-md text-slate-400 hover:text-white">
        <Filter className="w-3.5 h-3.5" />
      </button>
    </div>

    {/* T34：AI 生成节点入口（自然语言 → 服务端校验后的拓扑增量） */}
    <button
      type="button"
      onClick={onAiSuggest}
      className="mt-2 w-full flex items-center justify-center space-x-1.5 px-2.5 py-2 rounded-md bg-indigo-950/60 hover:bg-indigo-900/70 border border-indigo-400/40 hover:border-indigo-300/70 transition"
    >
      <Sparkles className="w-3.5 h-3.5 text-indigo-300" />
      <span className="text-xs text-indigo-200">AI 生成节点</span>
    </button>

    <div className="space-y-3 flex-1">
      {SIDEBAR_GROUPS.map((group) => {
        const filteredItems = group.items.filter((i) =>
          i.label.toLowerCase().includes(search.toLowerCase())
        );
        if (filteredItems.length === 0) return null;
        return (
          <div key={group.title}>
            <div className="flex items-center justify-between text-[11px] text-slate-300 font-medium mb-1.5 px-1">
              <span>▾ {group.title}</span>
              <ChevronDown className="w-3 h-3 text-slate-500" />
            </div>
            <div className="space-y-1.5">
              {filteredItems.map((item) => {
                const IconComponent = item.icon;
                return (
                  <button
                    key={item.id}
                    onClick={() => onAddItem(item)}
                    className="w-full flex items-center space-x-2 px-2.5 py-1.5 rounded-md bg-[#162038]/80 hover:bg-[#1e2c4c] border border-slate-700/60 hover:border-cyan-400/50 text-left transition group"
                  >
                    <IconComponent className="w-3.5 h-3.5 text-cyan-400 group-hover:scale-110 transition" />
                    <span className="text-xs text-slate-200 truncate">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  </aside>
);
