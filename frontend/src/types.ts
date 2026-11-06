// frontend/src/types.ts —— T40：工作台共享类型与初始拓扑（自 Workbench.tsx 抽出）
export interface NodePosition {
  x: number;
  y: number;
}

export interface WorkflowNode {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  position: NodePosition;
  theme_color: string;
  status: string;
  progress: number;
  confidence: number;
  latency_ms: number;
  config_json: Record<string, any>;
  last_error?: string | null;
  degraded?: boolean;
}

export interface NeuralEdge {
  id: string;
  source: string;
  target: string;
  latency_ms: number;
  confidence_pct: number;
  connection_status: string;
  active_pulse: boolean;
}

export interface RadarMetrics {
  radar_perception: number;
  responsiveness: number;
  accuracy: number;
  concurrency: number;
  stability: number;
}

export interface RunRecord {
  round_id: string;
  started_at: string;
  finished_at: string;
  nodes: { id: string; status: string; latency_ms: number; error: string | null }[];
}

export type ProjectStatus = '已就绪' | '运行中' | '已暂停' | '调试中' | '异常';

export const INITIAL_NODES: WorkflowNode[] = [
  {
    id: 'node_event_capturer',
    type: 'event_capturer',
    title: '事件捕获',
    subtitle: '(Event Capturer)',
    position: { x: 55, y: 235 },
    theme_color: '#10b981',
    status: 'active',
    progress: 100,
    confidence: 99.2,
    latency_ms: 8,
    config_json: {
      name: 'EventCapturer.eod',
      anenet5: {
        enalen: 'Pna',
        data: { name: '事件流监听器', type: '准确度', temndary: 'DOM Event Stream' },
      },
    },
  },
  {
    id: 'node_intent_agent',
    type: 'intent_agent',
    title: '意图识别智能体',
    subtitle: '(Intent Agent)',
    position: { x: 305, y: 235 },
    theme_color: '#6366f1',
    status: 'active',
    progress: 100,
    confidence: 99.2,
    latency_ms: 8,
    config_json: {
      name: 'IntentRouter.eod',
      anenet5: {
        enalen: 'Pna',
        data: { name: '意图识别I', type: '准确度', temndary: 'Semantic Routing' },
      },
    },
  },
  {
    id: 'node_ui_gen',
    type: 'ui_generation',
    title: '前端UI生成',
    subtitle: '(UI Generation Agent)',
    position: { x: 610, y: 95 },
    theme_color: '#38bdf8',
    status: 'active',
    progress: 98.6,
    confidence: 98.6,
    latency_ms: 8,
    config_json: {
      name: 'Agentinightik.eod',
      anenet5: {
        enalen: 'Pna',
        data: { name: '智能体I', type: '准确度', temndary: 'UI Generation' },
      },
    },
  },
  {
    id: 'node_co_agent',
    type: 'co_agent',
    title: '多Agent协作器',
    subtitle: '(Co-Agent)',
    position: { x: 610, y: 305 },
    theme_color: '#a855f7',
    status: 'active',
    progress: 99.2,
    confidence: 99.2,
    latency_ms: 8,
    config_json: {
      name: 'CoAgentSync.eod',
      anenet5: {
        enalen: 'Pna',
        data: { name: '多智能体协同总线', type: '并发度', temndary: 'Multi-Agent Consensus' },
      },
    },
  },
  {
    id: 'node_dom_renderer',
    type: 'dom_renderer',
    title: '页面渲染引擎',
    subtitle: '(DOM Renderer)',
    position: { x: 610, y: 435 },
    theme_color: '#3b82f6',
    status: 'success',
    progress: 100,
    confidence: 99.2,
    latency_ms: 8,
    config_json: {
      name: 'DOMHydrator.eod',
      anenet5: {
        enalen: 'Pna',
        data: { name: '渲染引擎I', type: '稳定度', temndary: 'Virtual DOM Hydration' },
      },
    },
  },
];

export const INITIAL_EDGES: NeuralEdge[] = [
  { id: 'edge_1_2', source: 'node_event_capturer', target: 'node_intent_agent', latency_ms: 8, confidence_pct: 99.2, connection_status: '已连接', active_pulse: true },
  { id: 'edge_2_3a', source: 'node_intent_agent', target: 'node_ui_gen', latency_ms: 8, confidence_pct: 99.2, connection_status: '已连接', active_pulse: true },
  { id: 'edge_2_3b', source: 'node_intent_agent', target: 'node_co_agent', latency_ms: 8, confidence_pct: 99.2, connection_status: '已连接', active_pulse: true },
  { id: 'edge_2_3c', source: 'node_intent_agent', target: 'node_dom_renderer', latency_ms: 8, confidence_pct: 99.2, connection_status: '已连接', active_pulse: true },
];
