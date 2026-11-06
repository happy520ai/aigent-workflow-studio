// frontend/src/Workbench.tsx
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Play,
  Pause,
  Zap,
  Search,
  Filter,
  Layers,
  Database,
  Cpu,
  FileCode,
  Share2,
  Clock,
  Settings,
  ChevronDown,
  Eye,
  MessageSquare,
  Network,
  Code,
  ArrowLeftRight,
  LayoutGrid,
  Terminal,
  FlaskConical,
  Rocket,
  X,
  Sparkles,
  Trash2,
  RefreshCw,
  Unplug,
} from 'lucide-react';
import { BioluminescentCanvas } from './components/BioluminescentCanvas';
import {
  PhosphorECGWidget,
  AuraAICoreWidget,
  WireframeScannerWidget,
  RadarSweepWidget,
} from './components/NodeMicroWidgets';
import { SandboxAndTimeTravelModal } from './components/SandboxAndTimeTravel';
import { useSynapseLinker } from './hooks/useSynapseLinker';
import { API_BASE, WS_URL, adminHeaders, buildWsUrl } from './config';
import { computeLayeredLayout } from './utils/layout';

interface NodePosition {
  x: number;
  y: number;
}

interface WorkflowNode {
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
}

interface NeuralEdge {
  id: string;
  source: string;
  target: string;
  latency_ms: number;
  confidence_pct: number;
  connection_status: string;
  active_pulse: boolean;
}

interface RadarMetrics {
  radar_perception: number;
  responsiveness: number;
  accuracy: number;
  concurrency: number;
  stability: number;
}

interface RunRecord {
  round_id: string;
  started_at: string;
  finished_at: string;
  nodes: { id: string; status: string; latency_ms: number; error: string | null }[];
}

type ProjectStatus = '已就绪' | '运行中' | '已暂停' | '调试中' | '异常';

// 顶部导航栏专用的 60FPS 荧光渐变迷你示波器组件 (还原 CPU 与内存实标动态曲线)
const HeaderMiniOscilloscope: React.FC<{
  series: number[];
  strokeColor: string;
  fillColor: string;
  showDashedBaseline?: boolean;
}> = ({ series, strokeColor, fillColor, showDashedBaseline }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (showDashedBaseline) {
      ctx.save();
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.75)';
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.moveTo(0, h * 0.72);
      ctx.lineTo(w, h * 0.72);
      ctx.stroke();
      ctx.restore();
    }

    if (series.length < 2) return;

    const coords = series.map((val, idx) => {
      const x = (idx / (series.length - 1)) * w;
      const norm = Math.max(0.08, Math.min(0.92, (val - 15) / 80));
      const y = h - norm * h;
      return { x, y };
    });

    // 绘制曲线下方荧光渐变填充
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, fillColor);
    grad.addColorStop(1, 'rgba(7, 10, 18, 0)');

    ctx.beginPath();
    ctx.moveTo(coords[0].x, h);
    coords.forEach((pt) => ctx.lineTo(pt.x, pt.y));
    ctx.lineTo(coords[coords.length - 1].x, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // 绘制高亮平滑曲线
    ctx.save();
    ctx.beginPath();
    coords.forEach((pt, idx) => {
      if (idx === 0) ctx.moveTo(pt.x, pt.y);
      else ctx.lineTo(pt.x, pt.y);
    });
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1.6;
    ctx.shadowColor = strokeColor;
    ctx.shadowBlur = 6;
    ctx.stroke();
    ctx.restore();
  }, [series, strokeColor, fillColor, showDashedBaseline]);

  return <canvas ref={canvasRef} width={82} height={24} className="block" />;
};

const INITIAL_NODES: WorkflowNode[] = [
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

const INITIAL_EDGES: NeuralEdge[] = [
  { id: 'edge_1_2', source: 'node_event_capturer', target: 'node_intent_agent', latency_ms: 8, confidence_pct: 99.2, connection_status: '已连接', active_pulse: true },
  { id: 'edge_2_3a', source: 'node_intent_agent', target: 'node_ui_gen', latency_ms: 8, confidence_pct: 99.2, connection_status: '已连接', active_pulse: true },
  { id: 'edge_2_3b', source: 'node_intent_agent', target: 'node_co_agent', latency_ms: 8, confidence_pct: 99.2, connection_status: '已连接', active_pulse: true },
  { id: 'edge_2_3c', source: 'node_intent_agent', target: 'node_dom_renderer', latency_ms: 8, confidence_pct: 99.2, connection_status: '已连接', active_pulse: true },
];

// WS 重连循环的代际锁：同一页面只允许最新挂载的 effect 循环持有连接。
// Vite HMR（React Refresh）可能遗留 detached fiber 的旧循环，旧循环在
// 下次触发时发现代际不符即静默退出，避免出现双连接与指示灯错乱。
let wsLoopGeneration = 0;
let moduleWs: WebSocket | null = null;

const SIDEBAR_GROUPS = [
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

export default function Workbench() {
  const [projectStatus, setProjectStatus] = useState<ProjectStatus>('运行中');
  const [nodes, setNodes] = useState<WorkflowNode[]>(INITIAL_NODES);
  const [edges, setEdges] = useState<NeuralEdge[]>(INITIAL_EDGES);
  const [selectedNodeId, setSelectedNodeId] = useState<string>('node_ui_gen');
  const [sidebarSearch, setSidebarSearch] = useState<string>('');
  const [globalSearch, setGlobalSearch] = useState<string>('');

  const [showSandboxModal, setShowSandboxModal] = useState<boolean>(false);
  const [activeMiniDrawer, setActiveMiniDrawer] = useState<'none' | 'memory' | 'topology' | 'settings'>('none');
  const [sharedMemoryBus, setSharedMemoryBus] = useState<Record<string, any>>({
    last_event: 'USER_CLICK_GENERATE_DASHBOARD',
    intent: 'create_cyber_analytics_card',
    co_agent_review: 'PASS_WITH_99.2%_CONFIDENCE',
    dom_hydration_status: 'READY',
  });

  // 大模型设置表单：不再内置明文默认值，打开设置抽屉时由 GET /settings/llm 回填
  const [llmForm, setLlmForm] = useState({ api_key: '', api_base: '', model: '', key_hint: '' });
  const [llmMsg, setLlmMsg] = useState<string>('');
  // 管理令牌仅存 sessionStorage，随请求头 X-Admin-Token 发送
  const [adminToken, setAdminToken] = useState<string>(() => sessionStorage.getItem('aigent_admin_token') ?? '');

  const [cpuSeries, setCpuSeries] = useState<number[]>([35, 58, 28, 72, 40, 63, 34, 76, 48, 65, 39, 58]);
  const [ecgSeries, setEcgSeries] = useState<number[]>([]);
  const [streamInfo, setStreamInfo] = useState<{ nodeId: string; text: string } | null>(null);
  // T32(32c)：多工作流切换器状态
  const [workflows, setWorkflows] = useState<{ id: string; name: string }[]>([]);
  const [activeWorkflowId, setActiveWorkflowId] = useState<string>('default');
  const [memSeries, setMemSeries] = useState<number[]>([62, 64, 63, 66, 64, 67, 65, 68, 66, 67, 65, 68]);
  const [radar, setRadar] = useState<RadarMetrics>({
    radar_perception: 92,
    responsiveness: 96,
    accuracy: 99.2,
    concurrency: 88,
    stability: 95,
  });
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    'Agent initialized: 99.2%...',
    'Agent initialized: 99.2%...',
    'Agent initialized: 99.2%...',
    'Agent initialized: 99.2%...',
    'Agent initialized: 99.2%...',
    'Agent initialized: 99.2%...',
    'Agent initialized: 99.2%...',
    'Success...',
    '[System] Deploying to Sandbox...',
    '[System] Deploying to Sandbox...',
  ]);
  const [jsonDraft, setJsonDraft] = useState<string>('');

  // WebSocket 连接状态：一次建立连接，断线指数退避重连
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [runHistory, setRunHistory] = useState<RunRecord[]>([]);

  // 最新状态镜像：WS 回调与本地仿真定时器读取，避免闭包过期
  const projectStatusRef = useRef<ProjectStatus>(projectStatus);
  const wsConnectedRef = useRef<boolean>(false);
  const nodesRef = useRef<WorkflowNode[]>(nodes);
  const draggingRef = useRef<string | null>(null);

  useEffect(() => {
    projectStatusRef.current = projectStatus;
  }, [projectStatus]);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  const pushLog = useCallback((line: string) => {
    setTerminalLogs((prev) => [...prev.slice(-9), line]);
  }, []);

  // ======================= T32(32c)：多工作流切换器 =======================
  const refreshWorkflows = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/workflows`, { headers: adminHeaders() });
      if (res.ok) setWorkflows(await res.json());
    } catch {
      // 后端未启动（离线仿真）时静默
    }
  }, []);

  const activateWorkflow = useCallback(
    async (id: string) => {
      if (!id || id === activeWorkflowId) return;
      try {
        const res = await fetch(`${API_BASE}/workflows/${encodeURIComponent(id)}/activate`, {
          method: 'POST',
          headers: adminHeaders(),
        });
        if (!res.ok) throw new Error(`activate ${id} failed: ${res.status}`);
        const snap = await res.json();
        setActiveWorkflowId(snap.workflow_id ?? id);
        setNodes(snap.nodes ?? []);
        setEdges(snap.edges ?? []);
        setTerminalLogs(snap.terminal_logs ?? []);
        pushLog(`[Workflow] 已切换到工作流 ${snap.workflow_id ?? id}`);
        void refreshWorkflows();
      } catch (err) {
        pushLog(`[Error] 切换工作流失败: ${String(err)}`);
      }
    },
    [activeWorkflowId, pushLog, refreshWorkflows]
  );

  const createWorkflow = useCallback(async () => {
    const name = window.prompt('新工作流名称', '新工作流');
    if (!name) return;
    try {
      const res = await fetch(`${API_BASE}/workflows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...adminHeaders() },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) throw new Error(`create failed: ${res.status}`);
      const wf = await res.json();
      await refreshWorkflows();
      await activateWorkflow(wf.id);
    } catch (err) {
      pushLog(`[Error] 新建工作流失败: ${String(err)}`);
    }
  }, [activateWorkflow, pushLog, refreshWorkflows]);

  useEffect(() => {
    void refreshWorkflows();
  }, [refreshWorkflows]);

  // T35：Kahn 分层自动布局 → 批量落位
  const handleAutoLayout = useCallback(async () => {
    const positions = computeLayeredLayout(nodesRef.current, edges);
    if (positions.length === 0) return;
    try {
      const res = await fetch(`${API_BASE}/workflow/positions`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...adminHeaders() },
        body: JSON.stringify({ positions }),
      });
      if (!res.ok) {
        pushLog(`[Error] 自动布局失败: ${res.status}`);
        return;
      }
      setNodes((prev) =>
        prev.map((n) => {
          const p = positions.find((q) => q.id === n.id);
          return p ? { ...n, position: { x: p.x, y: p.y } } : n;
        })
      );
      pushLog('[Layout] 已按拓扑层级自动排列节点');
    } catch (err) {
      pushLog(`[Error] 自动布局失败: ${String(err)}`);
    }
  }, [edges, pushLog]);

  // T34：AI 生成节点——自然语言 → 服务端校验应用后刷新快照
  const handleAiSuggest = useCallback(async () => {
    const prompt = window.prompt('描述你想要的智能体流程（例如：先解析意图，再调用 HTTP 拉取数据）', '');
    if (!prompt) return;
    pushLog('[AI-Suggest] 正在生成节点建议...');
    try {
      const res = await fetch(`${API_BASE}/workflow/ai-suggest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...adminHeaders() },
        body: JSON.stringify({ prompt }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        pushLog(`[Error] AI 建议被拒绝: ${body.detail ?? res.status}`);
        return;
      }
      pushLog(`[AI-Suggest] 已新增 ${body.added_nodes} 节点 / ${body.added_edges} 连线`);
      const snapRes = await fetch(`${API_BASE}/workflow`, { headers: adminHeaders() });
      if (snapRes.ok) {
        const snap = await snapRes.json();
        setNodes(snap.nodes);
        setEdges(snap.edges);
      }
    } catch (err) {
      pushLog(`[Error] AI 建议失败: ${String(err)}`);
    }
  }, [pushLog]);

  const { linkingSourceId, handleNodeShiftClick, persistNodePosition } = useSynapseLinker(
    API_BASE,
    (newEdge) => {
      setEdges((prev) => [...prev, newEdge]);
      pushLog(`[Synapse] 已建立突触连线: ${newEdge.source} -> ${newEdge.target}`);
    },
    (msg) => pushLog(`[Error] 连线失败: ${msg}`)
  );

  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const dragOffsetRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  useEffect(() => {
    draggingRef.current = draggingNodeId;
  }, [draggingNodeId]);

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) || nodes[2],
    [nodes, selectedNodeId]
  );

  // 仅在切换选中节点或其配置内容真实变化时重置草稿：
  // node_update 心跳会替换节点对象引用，若依赖对象本身会不断打断用户编辑
  const selectedConfigKey = JSON.stringify(selectedNode?.config_json ?? {});
  useEffect(() => {
    setJsonDraft(
      selectedConfigKey === "{}" ? "{}" : JSON.stringify(JSON.parse(selectedConfigKey), null, 2)
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeId, selectedConfigKey]);

  // ==================== WebSocket 实时遥测（依赖 []：一次建立，指数退避重连） ====================
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let retry = 0;
    let disposed = false;

    // 抢占代际：本 effect 成为唯一持有连接的循环；并终结遗留循环的旧连接
    const generation = ++wsLoopGeneration;
    if (moduleWs) {
      try {
        moduleWs.onclose = null;
        moduleWs.close();
      } catch {
        // 遗留连接已关闭则忽略
      }
      moduleWs = null;
    }

    const connect = () => {
      if (disposed || generation !== wsLoopGeneration) return;
      try {
        ws = new WebSocket(buildWsUrl());
        moduleWs = ws;
      } catch {
        scheduleReconnect();
        return;
      }

      ws.onopen = () => {
        retry = 0;
        wsConnectedRef.current = true;
        setWsConnected(true);
      };
      ws.onclose = () => {
        wsConnectedRef.current = false;
        setWsConnected(false);
        scheduleReconnect();
      };
      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          // 忽略关闭异常，由 onclose 统一调度重连
        }
      };
      ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.event === 'workflow_snapshot') {
          // T32：快照携带所属工作流，驱动切换器回显
          if (msg.data.workflow_id) setActiveWorkflowId(msg.data.workflow_id);
          setProjectStatus(msg.data.project_status);
          // 拖拽中的节点沿用本地坐标，避免被整张快照拽走
          setNodes(
            (msg.data.nodes as WorkflowNode[]).map((n) => {
              if (draggingRef.current === n.id) {
                const local = nodesRef.current.find((x) => x.id === n.id);
                return local ? { ...n, position: local.position } : n;
              }
              return n;
            })
          );
          setEdges(msg.data.edges);
          setTerminalLogs(msg.data.terminal_logs);
        } else if (msg.event === 'telemetry_tick') {
          setProjectStatus(msg.data.project_status);
          setCpuSeries(msg.data.cpu_history);
          setMemSeries(msg.data.memory_history);
          setRadar(msg.data.radar_metrics);
          setEcgSeries(msg.data.ecg_waveform ?? []); // T27：真实 DAG 轮延迟序列
          // A8 遥测瘦身：telemetry_tick 不再携带 shared_memory_bus
        } else if (msg.event === 'node_update') {
          const n = msg.data.node;
          setNodes((prev) =>
            prev.map((x) =>
              x.id === n.id
                ? { ...x, ...n, position: draggingRef.current === n.id ? x.position : n.position }
                : x
            )
          );
          // T31：最终态到达，结束该节点的流式显示
          setStreamInfo((prev) => (prev && prev.nodeId === n.id ? null : prev));
          if (msg.data.shared_memory_bus) setSharedMemoryBus(msg.data.shared_memory_bus);
        } else if (msg.event === 'node_stream') {
          // T31：LLM 增量输出（node_id + delta），右侧面板实时累积显示
          const { node_id: streamNodeId, delta } = msg.data;
          setStreamInfo((prev) =>
            prev && prev.nodeId === streamNodeId
              ? { nodeId: streamNodeId, text: prev.text + delta }
              : { nodeId: streamNodeId, text: delta }
          );
        } else if (msg.event === 'terminal_log') {
          setTerminalLogs(msg.data.logs);
        }
      };
    };

    const scheduleReconnect = () => {
      if (disposed || generation !== wsLoopGeneration) return;
      const delay = Math.min(15000, 1000 * Math.pow(2, retry));
      retry += 1;
      reconnectTimer = window.setTimeout(connect, delay);
    };

    connect();

    // 本地仿真回退内核：后端未连接时驱动 CPU/内存曲线（读取 ref 避免闭包过期）
    const fallbackTimer = window.setInterval(() => {
      if (wsConnectedRef.current || projectStatusRef.current === '已暂停') return;
      setCpuSeries((prev) => [...prev.slice(1), Math.round(28 + Math.random() * 52)]);
      setMemSeries((prev) => [...prev.slice(1), +(60 + Math.random() * 9).toFixed(1)]);
    }, 450);

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
      if (moduleWs === ws) moduleWs = null;
      clearInterval(fallbackTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ==================== 控制指令（运行/暂停/调试/重置） ====================
  const handleControl = async (action: 'run' | 'pause' | 'debug' | 'reset') => {
    if (action === 'run') setProjectStatus('运行中');
    if (action === 'pause') setProjectStatus('已暂停');
    if (action === 'debug') {
      setProjectStatus('调试中');
      pushLog(`[Debug] 单步神经元脉冲已触发 @ ${new Date().toLocaleTimeString()}`);
    }
    if (action === 'reset') {
      if (!window.confirm('确认重置拓扑与沙盒到默认状态？')) return;
      pushLog('[System] 正在重置神经元拓扑...');
    }
    try {
      await fetch(`${API_BASE}/workflow/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
    } catch {
      // 本地仿真直接接管
    }
  };

  // ==================== 侧栏算子注入：后端在线走 POST，离线本地仿真 ====================
  const handleAddComponentNode = async (item: { id: string; label: string; color: string }) => {
    if (item.id === 'dep_test') {
      setShowSandboxModal(true);
      return;
    }
    if (item.id === 'dep_publish') {
      window.open(`${API_BASE}/publish/export-zip`, '_blank');
      pushLog('[Publish] 正在导出独立前端工程 ZIP 包...');
      return;
    }

    const randomY = Math.floor(130 + Math.random() * 330);

    if (wsConnected) {
      try {
        const res = await fetch(`${API_BASE}/workflow/nodes`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            component_id: item.id,
            x: 455,
            y: randomY,
            connect_from: selectedNodeId || null,
          }),
        });
        if (res.ok) {
          const created: WorkflowNode = await res.json();
          setNodes((prev) =>
            prev.some((n) => n.id === created.id)
              ? prev.map((n) => (n.id === created.id ? created : n))
              : [...prev, created]
          );
          setSelectedNodeId(created.id);
          pushLog(`[Topology] 已挂载神经元节点: ${item.label}`);
        } else {
          pushLog(`[Error] 添加节点失败: HTTP ${res.status}`);
        }
      } catch {
        pushLog('[Error] 添加节点失败: 网络异常');
      }
      return;
    }

    // 离线仿真：本地创建，id 加 local_ 前缀与后端节点区分
    const newId = `local_node_${item.id}_${Math.floor(Math.random() * 900 + 100)}`;
    const newNode: WorkflowNode = {
      id: newId,
      type: item.id,
      title: item.label.split(' ')[0],
      subtitle: `(${item.label.split('(')[1] || 'Agent)'}`,
      position: { x: 455, y: randomY },
      theme_color: item.color,
      status: 'active',
      progress: 99.0,
      confidence: 99.2,
      latency_ms: 8,
      config_json: {
        name: `${item.id}.eod`,
        anenet5: { enalen: 'Pna', data: { name: item.label, type: '准确度', temndary: 'Dynamic Node' } },
      },
    };
    setNodes((prev) => [...prev, newNode]);
    setEdges((prev) => [
      ...prev,
      {
        id: `edge_${newId}`,
        source: 'node_intent_agent',
        target: newId,
        latency_ms: 8,
        confidence_pct: 99.2,
        connection_status: '已连接',
        active_pulse: true,
      },
    ]);
    setSelectedNodeId(newId);
    pushLog(`[Topology] [本地仿真] 已挂载神经元节点: ${item.label}`);
  };

  // ==================== 节点与连线删除（拓扑抽屉 / 检视器 / Delete 键共用） ====================
  const handleDeleteNode = useCallback(
    async (nodeId: string) => {
      if (!nodeId) return;
      try {
        const res = await fetch(`${API_BASE}/workflow/nodes/${nodeId}`, { method: 'DELETE' });
        if (res.ok) {
          setNodes((prev) => prev.filter((n) => n.id !== nodeId));
          setEdges((prev) => prev.filter((e) => e.source !== nodeId && e.target !== nodeId));
          setSelectedNodeId((prev) => (prev === nodeId ? '' : prev));
          pushLog(`[Topology] 已删除节点 ${nodeId}`);
        } else {
          pushLog(`[Error] 删除节点失败: HTTP ${res.status}`);
        }
      } catch {
        pushLog('[Error] 删除节点失败: 网络异常');
      }
    },
    [API_BASE, pushLog]
  );

  const handleDeleteEdge = useCallback(
    async (edgeId: string) => {
      try {
        const res = await fetch(`${API_BASE}/workflow/edges/${edgeId}`, { method: 'DELETE' });
        if (res.ok) {
          setEdges((prev) => prev.filter((e) => e.id !== edgeId));
          pushLog(`[Synapse] 已断开连线 ${edgeId}`);
        } else {
          pushLog(`[Error] 断开连线失败: HTTP ${res.status}`);
        }
      } catch {
        pushLog('[Error] 断开连线失败: 网络异常');
      }
    },
    [API_BASE, pushLog]
  );

  // 选中节点后按 Delete 删除（输入框聚焦时不触发）
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Delete' || !selectedNodeId) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (window.confirm(`确认删除节点 ${selectedNodeId}？`)) {
        handleDeleteNode(selectedNodeId);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedNodeId, handleDeleteNode]);

  // ==================== 拓扑抽屉：最近运行记录 ====================
  const fetchRunHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/runs?limit=5`);
      if (res.ok) {
        setRunHistory(await res.json());
      }
    } catch {
      // 离线时保留上次记录
    }
  }, [API_BASE]);

  useEffect(() => {
    if (activeMiniDrawer === 'topology' && wsConnected) {
      fetchRunHistory();
    }
  }, [activeMiniDrawer, wsConnected, fetchRunHistory]);

  // ==================== 设置抽屉：大模型配置读取与更新 ====================
  const fetchLlmSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/llm`, {
        headers: adminToken ? { 'X-Admin-Token': adminToken } : {},
      });
      if (res.ok) {
        const data = await res.json();
        // api_key 留空表示不修改；其余由后端回填
        setLlmForm({
          api_key: '',
          api_base: data.api_base ?? '',
          model: data.model ?? '',
          key_hint: data.key_hint ?? '',
        });
        setLlmMsg(`当前密钥: ${data.key_hint || '未设置'} | has_key: ${data.has_key}`);
      } else {
        setLlmMsg(`读取失败: HTTP ${res.status}`);
      }
    } catch {
      setLlmMsg('读取失败: 网络异常');
    }
  }, [API_BASE, adminToken]);

  useEffect(() => {
    if (activeMiniDrawer === 'settings' && wsConnected) {
      fetchLlmSettings();
    }
  }, [activeMiniDrawer, wsConnected, fetchLlmSettings]);

  const handleUpdateLlmSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/llm`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(adminToken ? { 'X-Admin-Token': adminToken } : {}),
        },
        body: JSON.stringify({
          api_key: llmForm.api_key,
          api_base: llmForm.api_base,
          model: llmForm.model,
        }),
      });
      if (res.ok) {
        setLlmMsg('已更新');
        pushLog('[Settings] 已更新智能体大模型驱动内核');
        fetchLlmSettings();
      } else {
        let detail = `HTTP ${res.status}`;
        try {
          const err = await res.json();
          detail = err.detail ?? detail;
        } catch {
          // 保留 HTTP 状态码
        }
        setLlmMsg(`更新失败: ${detail}`);
        pushLog(`[Error] 更新模型配置失败: ${detail}`);
      }
    } catch {
      setLlmMsg('更新失败: 网络异常');
    }
  };

  const handleAdminTokenChange = (value: string) => {
    setAdminToken(value);
    sessionStorage.setItem('aigent_admin_token', value);
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!draggingNodeId) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const nextX = Math.max(10, Math.min(rect.width - 230, e.clientX - rect.left - dragOffsetRef.current.x));
    const nextY = Math.max(10, Math.min(rect.height - 150, e.clientY - rect.top - dragOffsetRef.current.y));
    setNodes((prev) =>
      prev.map((n) => (n.id === draggingNodeId ? { ...n, position: { x: nextX, y: nextY } } : n))
    );
  };

  const handleCanvasMouseUp = () => {
    if (draggingNodeId) {
      const dragged = nodes.find((n) => n.id === draggingNodeId);
      if (dragged) {
        persistNodePosition(dragged.id, dragged.position.x, dragged.position.y);
      }
    }
    setDraggingNodeId(null);
  };

  const statusColorClass =
    projectStatus === '运行中'
      ? 'text-emerald-400'
      : projectStatus === '已暂停'
      ? 'text-pink-400'
      : projectStatus === '调试中'
      ? 'text-cyan-400'
      : projectStatus === '异常'
      ? 'text-red-400'
      : 'text-slate-300';

  return (
    <div className="w-screen h-screen overflow-hidden bg-[#070a12] text-slate-100 flex flex-col font-sans select-none">
      {/* ==================== 1. 顶部全局导航栏 ==================== */}
      <header className="h-[60px] w-full bg-[#0b101d]/95 border-b border-slate-800/80 px-4 flex items-center justify-between z-30">
        <div className="flex items-center space-x-3">
          <div className="relative w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-950 via-purple-900 to-cyan-900 flex items-center justify-center shadow-[0_0_18px_rgba(56,189,248,0.55)] border border-cyan-400/50">
            <Sparkles className="w-5 h-5 text-cyan-300 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-[18px] font-bold tracking-wide text-white">
                前端智能体工作流平台
              </span>
              <span className="text-slate-500 font-light">|</span>
            </div>
            <div className="text-[10px] tracking-widest text-slate-400 font-mono">
              AIGENT-WORKFLOW STUDIO v2.8
            </div>
          </div>

          {/* T32(32c)：多工作流切换器 */}
          <div className="flex items-center gap-1.5 ml-4">
            <select
              aria-label="切换工作流"
              value={activeWorkflowId}
              onChange={(e) => void activateWorkflow(e.target.value)}
              className="px-2 py-1 rounded-md bg-slate-900/80 border border-slate-600/70 text-[11px] text-slate-200 font-mono outline-none focus:border-cyan-400/70 max-w-40"
            >
              {workflows.length === 0 && <option value={activeWorkflowId}>{activeWorkflowId}</option>}
              {workflows.map((wf) => (
                <option key={wf.id} value={wf.id}>
                  {wf.name || wf.id}
                </option>
              ))}
            </select>
            <button
              type="button"
              aria-label="新建工作流"
              onClick={() => void createWorkflow()}
              title="新建工作流"
              className="px-2 py-1 rounded-md bg-slate-900/80 border border-slate-600/70 text-[11px] text-cyan-300 font-mono hover:border-cyan-400/70 transition"
            >
              + 新建
            </button>
            {/* T35：Kahn 分层自动布局 */}
            <button
              type="button"
              aria-label="自动布局"
              onClick={() => void handleAutoLayout()}
              title="按拓扑层级自动排列节点"
              className="px-2 py-1 rounded-md bg-slate-900/80 border border-slate-600/70 text-[11px] text-emerald-300 font-mono hover:border-emerald-400/70 transition"
            >
              ⌗ 自动布局
            </button>
          </div>
        </div>

        {/* 中部运行/暂停/调试发光按钮组 + 连接指示灯 */}
        <div className="flex items-center space-x-3">
          <button
            onClick={() => handleControl('run')}
            className="px-3.5 py-1.5 rounded-lg bg-emerald-950/50 border border-emerald-400/90 text-emerald-300 flex items-center space-x-2 shadow-[0_0_16px_rgba(16,185,129,0.45),inset_0_0_8px_rgba(16,185,129,0.2)] hover:bg-emerald-900/60 transition"
          >
            <Play className="w-3.5 h-3.5 fill-emerald-400" />
            <div className="text-left leading-tight">
              <div className="text-xs font-semibold">运行</div>
              <div className="text-[9px] opacity-80">Run</div>
            </div>
          </button>

          <button
            onClick={() => handleControl('pause')}
            className="px-3.5 py-1.5 rounded-lg bg-pink-950/40 border border-pink-500/90 text-pink-300 flex items-center space-x-2 shadow-[0_0_16px_rgba(236,72,153,0.4),inset_0_0_8px_rgba(236,72,153,0.2)] hover:bg-pink-900/50 transition"
          >
            <Pause className="w-3.5 h-3.5" />
            <div className="text-left leading-tight">
              <div className="text-xs font-semibold">暂停</div>
              <div className="text-[9px] opacity-80">Pause</div>
            </div>
          </button>

          <button
            onClick={() => handleControl('debug')}
            className="px-3.5 py-1.5 rounded-lg bg-blue-950/50 border border-blue-400/90 text-blue-300 flex items-center space-x-2 shadow-[0_0_16px_rgba(59,130,246,0.45),inset_0_0_8px_rgba(59,130,246,0.2)] hover:bg-blue-900/60 transition"
          >
            <Zap className="w-3.5 h-3.5" />
            <div className="text-left leading-tight">
              <div className="text-xs font-semibold">调试</div>
              <div className="text-[9px] opacity-80">Debug</div>
            </div>
          </button>

          <button
            onClick={() => handleControl('reset')}
            className="px-3.5 py-1.5 rounded-lg bg-slate-900/60 border border-slate-400/70 text-slate-200 flex items-center space-x-2 shadow-[0_0_12px_rgba(148,163,184,0.3)] hover:bg-slate-800/70 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <div className="text-left leading-tight">
              <div className="text-xs font-semibold">重置</div>
              <div className="text-[9px] opacity-80">Reset</div>
            </div>
          </button>

          {/* 后端连接指示灯：绿点=已连接后端，灰点=本地仿真 */}
          <div
            className="pl-3 text-xs text-slate-300 flex items-center space-x-1.5"
            title={wsConnected ? `WS: ${WS_URL}` : `等待后端 ${WS_URL}`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                wsConnected
                  ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.95)]'
                  : 'bg-slate-500'
              }`}
            />
            <span className={wsConnected ? 'text-emerald-300' : 'text-slate-400'}>
              {wsConnected ? '已连接后端' : '本地仿真'}
            </span>
          </div>

          <div className="pl-3 text-xs text-slate-300 flex items-center space-x-1.5 border-l border-slate-800">
            <span>项目状态:</span>
            <span className={`font-semibold ${statusColorClass}`}>{projectStatus}</span>
          </div>
        </div>

        {/* 右侧 60FPS 荧光示波器与全局搜索 */}
        <div className="flex items-center space-x-5">
          <div className="flex items-center space-x-4 border-l border-r border-slate-800 px-4 py-1">
            <div>
              <div className="text-[10px] text-slate-400 mb-0.5">CPU</div>
              <HeaderMiniOscilloscope
                series={cpuSeries}
                strokeColor="#38bdf8"
                fillColor="rgba(56, 189, 248, 0.28)"
              />
            </div>
            <div>
              <div className="text-[10px] text-slate-400 mb-0.5">内存实标</div>
              <HeaderMiniOscilloscope
                series={memSeries}
                strokeColor="#c084fc"
                fillColor="rgba(192, 132, 252, 0.22)"
                showDashedBaseline
              />
            </div>
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={globalSearch}
              onChange={(e) => setGlobalSearch(e.target.value)}
              placeholder="全局搜索"
              className="w-36 bg-[#131b2e] border border-slate-700/80 rounded-full py-1 pl-8 pr-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400"
            />
          </div>
        </div>
      </header>

      {/* ==================== 2. 主体四栏工作区 ==================== */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* 2.1 最左侧极窄图标导航栏 */}
        <aside className="w-12 bg-[#090d18] border-r border-slate-800/80 flex flex-col items-center py-3 justify-between z-30">
          <div className="flex flex-col items-center space-y-4">
            <button
              onClick={() => setActiveMiniDrawer('none')}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition ${
                activeMiniDrawer === 'none'
                  ? 'bg-blue-600/30 border border-blue-400/60 text-blue-300 shadow-[0_0_10px_rgba(59,130,246,0.4)]'
                  : 'hover:bg-slate-800/60 text-slate-400'
              }`}
            >
              <Layers className="w-4 h-4" />
            </button>
            <button
              onClick={() => setActiveMiniDrawer(activeMiniDrawer === 'memory' ? 'none' : 'memory')}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition ${
                activeMiniDrawer === 'memory'
                  ? 'bg-cyan-500/30 border border-cyan-400 text-cyan-300'
                  : 'hover:bg-slate-800/60 text-slate-400'
              }`}
            >
              <Database className="w-4 h-4" />
            </button>
            <button
              onClick={() => setActiveMiniDrawer(activeMiniDrawer === 'topology' ? 'none' : 'topology')}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition ${
                activeMiniDrawer === 'topology'
                  ? 'bg-purple-500/30 border border-purple-400 text-purple-300'
                  : 'hover:bg-slate-800/60 text-slate-400'
              }`}
            >
              <Cpu className="w-4 h-4" />
            </button>
            <button
              onClick={() => setShowSandboxModal(true)}
              className="w-8 h-8 rounded-lg hover:bg-slate-800/60 flex items-center justify-center text-slate-400 hover:text-cyan-300"
            >
              <Share2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => window.open(`${API_BASE}/publish/export-zip`, '_blank')}
              className="w-8 h-8 rounded-lg hover:bg-slate-800/60 flex items-center justify-center text-slate-400 hover:text-emerald-300"
            >
              <FileCode className="w-4 h-4" />
            </button>
            <button
              onClick={() => setShowSandboxModal(true)}
              className="w-8 h-8 rounded-lg hover:bg-cyan-950/60 flex items-center justify-center text-cyan-400"
            >
              <Sparkles className="w-4 h-4" />
            </button>
          </div>
          <div className="flex flex-col items-center space-y-4">
            <button
              onClick={() => setShowSandboxModal(true)}
              className="w-8 h-8 rounded-lg hover:bg-slate-800/60 flex items-center justify-center text-slate-400 hover:text-emerald-300"
            >
              <Clock className="w-4 h-4" />
            </button>
            <button
              onClick={() => setActiveMiniDrawer(activeMiniDrawer === 'settings' ? 'none' : 'settings')}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition ${
                activeMiniDrawer === 'settings'
                  ? 'bg-amber-500/30 border border-amber-400 text-amber-300'
                  : 'hover:bg-slate-800/60 text-slate-400'
              }`}
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </aside>

        {/* 2.1.5 迷你抽屉浮层：共享记忆总线 / 拓扑与运行记录 / 大模型设置 */}
        {activeMiniDrawer !== 'none' && (
          <div className="absolute left-12 top-0 bottom-0 w-[280px] bg-[#0d1322]/97 border-r border-slate-800/80 backdrop-blur-md z-40 flex flex-col p-3 space-y-3 overflow-y-auto">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-200">
                {activeMiniDrawer === 'memory' && '共享记忆总线 (Memory Bus)'}
                {activeMiniDrawer === 'topology' && '拓扑与运行记录 (Topology)'}
                {activeMiniDrawer === 'settings' && '大模型设置 (LLM Settings)'}
              </span>
              <button
                onClick={() => setActiveMiniDrawer('none')}
                className="p-1 rounded bg-slate-800/80 text-slate-400 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* —— 共享记忆总线 —— */}
            {activeMiniDrawer === 'memory' && (
              <pre className="flex-1 bg-[#080c16] border border-slate-800 rounded-lg p-2.5 font-mono text-[10px] text-cyan-300 whitespace-pre-wrap break-words overflow-y-auto leading-relaxed">
                {JSON.stringify(sharedMemoryBus, null, 2)}
              </pre>
            )}

            {/* —— 拓扑与运行记录 —— */}
            {activeMiniDrawer === 'topology' &&
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
                            onClick={() => handleDeleteNode(n.id)}
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
                            onClick={() => handleDeleteEdge(e.id)}
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
                        onClick={fetchRunHistory}
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

            {/* —— 大模型设置 —— */}
            {activeMiniDrawer === 'settings' &&
              (wsConnected ? (
                <div className="flex-1 flex flex-col space-y-2.5">
                  <div className="text-[10px] font-mono text-slate-500 break-all">
                    {llmMsg || '读取中...'}
                  </div>
                  <label className="text-[10px] text-slate-400">
                    api_key（留空表示不修改 {llmForm.key_hint ? `| 当前 ${llmForm.key_hint}` : ''}）
                    <input
                      type="password"
                      value={llmForm.api_key}
                      onChange={(e) => setLlmForm((f) => ({ ...f, api_key: e.target.value }))}
                      placeholder="sk-..."
                      className="mt-1 w-full bg-[#090e1a] border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-cyan-500"
                    />
                  </label>
                  <label className="text-[10px] text-slate-400">
                    api_base
                    <input
                      type="text"
                      value={llmForm.api_base}
                      onChange={(e) => setLlmForm((f) => ({ ...f, api_base: e.target.value }))}
                      className="mt-1 w-full bg-[#090e1a] border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-cyan-500"
                    />
                  </label>
                  <label className="text-[10px] text-slate-400">
                    model
                    <input
                      type="text"
                      value={llmForm.model}
                      onChange={(e) => setLlmForm((f) => ({ ...f, model: e.target.value }))}
                      className="mt-1 w-full bg-[#090e1a] border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-cyan-500"
                    />
                  </label>
                  <label className="text-[10px] text-slate-400">
                    管理令牌（可选，仅存 sessionStorage）
                    <input
                      type="password"
                      value={adminToken}
                      onChange={(e) => handleAdminTokenChange(e.target.value)}
                      placeholder="AIGENT_ADMIN_TOKEN"
                      className="mt-1 w-full bg-[#090e1a] border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-200 font-mono focus:outline-none focus:border-amber-500"
                    />
                  </label>
                  <button
                    onClick={handleUpdateLlmSettings}
                    className="w-full py-1.5 rounded-md bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 text-xs font-semibold hover:bg-cyan-500/30"
                  >
                    保存模型配置
                  </button>
                </div>
              ) : (
                <div className="flex-1 flex items-center justify-center text-[11px] text-slate-500">
                  仅后端在线时可用
                </div>
              ))}
          </div>
        )}

        {/* 2.2 左侧算子与组件库面板 */}
        <aside className="w-[230px] bg-[#0d1322]/90 border-r border-slate-800/80 p-3 flex flex-col overflow-y-auto z-20">
          <div className="flex items-center space-x-1.5 mb-3">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={sidebarSearch}
                onChange={(e) => setSidebarSearch(e.target.value)}
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
            onClick={() => void handleAiSuggest()}
            className="mt-2 w-full flex items-center justify-center space-x-1.5 px-2.5 py-2 rounded-md bg-indigo-950/60 hover:bg-indigo-900/70 border border-indigo-400/40 hover:border-indigo-300/70 transition"
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-300" />
            <span className="text-xs text-indigo-200">AI 生成节点</span>
          </button>

          <div className="space-y-3 flex-1">
            {SIDEBAR_GROUPS.map((group) => {
              const filteredItems = group.items.filter((i) =>
                i.label.toLowerCase().includes(sidebarSearch.toLowerCase())
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
                          onClick={() => handleAddComponentNode(item)}
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

        {/* 2.3 中央加色混合生物发光神经元画布 */}
        <main
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={handleCanvasMouseUp}
          className="flex-1 relative overflow-hidden bg-[#080c17]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        >
          {/* 60FPS 加色混合生物神经元 + 多股交织突触彗星脉冲引擎 */}
          <BioluminescentCanvas
            isRunning={projectStatus === '运行中'}
            nodes={nodes.map((n) => ({
              id: n.id,
              x: n.position.x,
              y: n.position.y,
              width: 195,
              themeColor: n.theme_color,
            }))}
            edges={edges.map((e) => ({
              id: e.id,
              source: e.source,
              target: e.target,
              latencyMs: e.latency_ms,
              confidencePct: e.confidence_pct,
              connectionStatus: e.connection_status,
              highlighted: e.source === selectedNodeId || e.target === selectedNodeId,
            }))}
          />

          {/* 画布神经元节点渲染层 */}
          {nodes
            .filter(
              (n) =>
                !globalSearch ||
                n.title.toLowerCase().includes(globalSearch.toLowerCase()) ||
                n.subtitle.toLowerCase().includes(globalSearch.toLowerCase())
            )
            .map((node) => {
              const isSelected = node.id === selectedNodeId;
              const isLinkSource = node.id === linkingSourceId;
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
                  key={node.id}
                  title={node.status === 'error' && node.last_error ? node.last_error : undefined}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    if (e.shiftKey) {
                      handleNodeShiftClick(node.id);
                      return;
                    }
                    setSelectedNodeId(node.id);
                    setDraggingNodeId(node.id);
                    dragOffsetRef.current = {
                      x: e.clientX - e.currentTarget.getBoundingClientRect().left,
                      y: e.clientY - e.currentTarget.getBoundingClientRect().top,
                    };
                  }}
                  style={{
                    left: `${node.position.x}px`,
                    top: `${node.position.y}px`,
                    borderColor,
                    boxShadow: isSelected
                      ? `0 0 24px ${node.theme_color}85, inset 0 0 14px ${node.theme_color}35`
                      : `0 0 15px ${node.theme_color}45, inset 0 0 8px ${node.theme_color}20`,
                  }}
                  className="absolute w-[195px] rounded-xl bg-[#0e1628]/80 backdrop-blur-md border p-3 cursor-grab active:cursor-grabbing z-20 transition-shadow"
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
                    ) : (node as { degraded?: boolean }).degraded ? (
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
                    <PhosphorECGWidget isRunning={projectStatus === '运行中'} waveform={ecgSeries} />
                  )}

                  {node.type === 'intent_agent' && (
                    <AuraAICoreWidget isRunning={projectStatus === '运行中'} />
                  )}

                  {node.type === 'ui_generation' && (
                    <WireframeScannerWidget
                      progress={node.progress}
                      isRunning={projectStatus === '运行中'}
                    />
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
                            setShowSandboxModal(true);
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
                    <span className={node.status === 'skipped' ? 'text-slate-500' : ''}>
                      {node.status}
                    </span>
                  </div>
                </div>
              );
            })}
        </main>

        {/* 2.4 右侧属性配置、五维扫描雷达、JSON 配置区与 AI 终端 */}
        <aside className="w-[310px] bg-[#0d1322]/95 border-l border-slate-800/80 flex flex-col justify-between p-3 space-y-3 z-20 overflow-y-auto">
          <div className="bg-[#121b2e]/90 border border-slate-800 rounded-xl p-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2">
              <span className="text-xs font-semibold text-slate-200">属性配置 (Inspector)</span>
              <button
                onClick={() => {
                  if (selectedNodeId && window.confirm(`确认删除节点 ${selectedNodeId}？`)) {
                    handleDeleteNode(selectedNodeId);
                  }
                }}
                title="删除节点"
                className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/40"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="text-[11px] text-slate-400 mb-1">属性配置 · {selectedNode?.title}</div>

            <RadarSweepWidget
              isRunning={projectStatus === '运行中'}
              metrics={[
                radar.radar_perception,
                radar.responsiveness,
                radar.accuracy,
                radar.concurrency,
                radar.stability,
              ]}
            />
          </div>

          <div className="bg-[#121b2e]/90 border border-slate-800 rounded-xl p-3 flex flex-col">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-slate-200">JSON 配置区</span>
              <button
                onClick={async () => {
                  let parsed: Record<string, any>;
                  try {
                    parsed = JSON.parse(jsonDraft);
                  } catch {
                    pushLog('[Error] JSON 语法校验未通过');
                    return;
                  }
                  // 后端在线走 PUT /config 以响应为准；离线保留本地更新
                  if (wsConnected) {
                    try {
                      const res = await fetch(`${API_BASE}/workflow/nodes/${selectedNode.id}/config`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(parsed),
                      });
                      if (res.ok) {
                        const updated: WorkflowNode = await res.json();
                        setNodes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
                        pushLog(`[Inspector] 已应用节点 ${selectedNode.title} 配置`);
                      } else {
                        pushLog(`[Error] 热更新失败: HTTP ${res.status}，保持原值`);
                      }
                    } catch {
                      pushLog('[Error] 热更新失败: 网络异常，保持原值');
                    }
                    return;
                  }
                  setNodes((prev) =>
                    prev.map((n) => (n.id === selectedNode.id ? { ...n, config_json: parsed } : n))
                  );
                  pushLog(`[Inspector] [本地仿真] 已应用节点 ${selectedNode.title} 配置`);
                }}
                className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30"
              >
                热更新
              </button>
            </div>
            <textarea
              value={jsonDraft}
              onChange={(e) => setJsonDraft(e.target.value)}
              rows={7}
              spellCheck={false}
              className="w-full bg-[#090e1a] border border-slate-800 rounded-lg p-2 font-mono text-[11px] text-amber-300 focus:outline-none focus:border-cyan-500 resize-none leading-relaxed"
            />
          </div>

          <div className="bg-[#121b2e]/90 border border-slate-800 rounded-xl p-3 flex-1 flex flex-col min-h-[175px]">
            {/* T31：LLM 流式输出（node_stream 增量实时显示；node_update 最终态到达后收起） */}
            {streamInfo && (
              <div className="mb-2 rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-2">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  <span className="text-[10px] text-cyan-300 font-mono">流式输出 · {streamInfo.nodeId}</span>
                  <span className="text-[10px] text-slate-500">{streamInfo.text.length} 字符</span>
                </div>
                <pre className="text-[10px] font-mono text-cyan-100/90 whitespace-pre-wrap break-all max-h-28 overflow-y-auto">
                  {streamInfo.text}
                </pre>
              </div>
            )}
            <div className="text-xs font-semibold text-slate-200 mb-2">动态日志与 AI 终端</div>
            <div className="flex-1 bg-[#080c16] border border-slate-800/90 rounded-lg p-2.5 font-mono text-[11px] space-y-1 overflow-y-auto">
              {terminalLogs.map((line, idx) => {
                const isError = line.startsWith('[Error]') || line.startsWith('[Warn]');
                const isSystem =
                  line.startsWith('[System]') ||
                  line.startsWith('[Inspector]') ||
                  line.startsWith('[Publish]');
                const isDebug =
                  line.startsWith('[Debug]') ||
                  line.startsWith('[Time-Travel]') ||
                  line.startsWith('Success');
                return (
                  <div
                    key={idx}
                    className={
                      isError
                        ? 'text-rose-400'
                        : isSystem
                        ? 'text-amber-400'
                        : isDebug
                        ? 'text-cyan-300 font-semibold'
                        : 'text-emerald-400'
                    }
                  >
                    {line}
                  </div>
                );
              })}
              <span className="inline-block w-1.5 h-3 bg-emerald-400 animate-pulse ml-0.5" />
            </div>
          </div>
        </aside>
      </div>

      {/* ==================== 3. 实时 DOM 沙盒、AST 语法树自愈与时间旅行控制台 ==================== */}
      <SandboxAndTimeTravelModal
        isOpen={showSandboxModal}
        onClose={() => setShowSandboxModal(false)}
        onRestoreCheckpoint={async (ckpt) => {
          setSelectedNodeId(ckpt.node_id);
          setSharedMemoryBus(ckpt.state_payload);
          pushLog(`[Time-Travel] 已恢复断点 ${ckpt.checkpoint_id}`);
          // 回滚后向后端拉取最新快照，节点与连线随断点还原
          try {
            const res = await fetch(`${API_BASE}/workflow`);
            if (res.ok) {
              const snap = await res.json();
              setNodes(snap.nodes);
              setEdges(snap.edges);
              setTerminalLogs(snap.terminal_logs);
              setProjectStatus(snap.project_status);
            }
          } catch {
            // 离线时保留本地状态
          }
        }}
      />
    </div>
  );
}
