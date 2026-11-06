// frontend/src/Workbench.tsx —— T40：组合根（状态与编排保留；类型/hooks/组件已拆分至独立模块）
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Play,
  Pause,
  Zap,
  Search,
  Layers,
  Database,
  Cpu,
  FileCode,
  Share2,
  Clock,
  Settings,
  Sparkles,
  Trash2,
  RefreshCw,
} from 'lucide-react';
import { BioluminescentCanvas } from './components/BioluminescentCanvas';
import { RadarSweepWidget } from './components/NodeMicroWidgets';
import { SandboxAndTimeTravelModal } from './components/SandboxAndTimeTravel';
import { HeaderMiniOscilloscope } from './components/HeaderMiniOscilloscope';
import { NodeCard } from './components/NodeCard';
import { ComponentLibrary } from './components/ComponentLibrary';
import { MiniDrawer } from './components/MiniDrawer';
import type { MiniDrawerKind } from './components/MiniDrawer';
import { TerminalLog } from './components/TerminalLog';
import { useSynapseLinker } from './hooks/useSynapseLinker';
import { useWorkflowSocket } from './hooks/useWorkflowSocket';
import { workflowApi } from './hooks/useWorkflowApi';
import { API_BASE, WS_URL, setAdminToken } from './config';
import { emitToast } from './components/Toast';
import { computeLayeredLayout } from './utils/layout';
import { usePrefersReducedMotion } from './hooks/usePrefersReducedMotion';
import {
  INITIAL_NODES,
  INITIAL_EDGES,
  type NeuralEdge,
  type ProjectStatus,
  type RadarMetrics,
  type RunRecord,
  type WorkflowNode,
} from './types';

// T44：拓扑命令（撤销/重做）。注意：删除后重加的节点/连线会获得新 id，重做链为近似还原。
type TopoCommand =
  | { kind: 'add_node'; node: WorkflowNode }
  | { kind: 'del_node'; node: WorkflowNode; edges: NeuralEdge[] }
  | { kind: 'add_edge'; edge: NeuralEdge }
  | { kind: 'del_edge'; edge: NeuralEdge };

export default function Workbench() {
  const [projectStatus, setProjectStatus] = useState<ProjectStatus>('运行中');
  const [nodes, setNodes] = useState<WorkflowNode[]>(INITIAL_NODES);
  const [edges, setEdges] = useState<NeuralEdge[]>(INITIAL_EDGES);
  const [selectedNodeId, setSelectedNodeId] = useState<string>('node_ui_gen');
  const [sidebarSearch, setSidebarSearch] = useState<string>('');
  const [globalSearch, setGlobalSearch] = useState<string>('');

  const [showSandboxModal, setShowSandboxModal] = useState<boolean>(false);
  const [activeMiniDrawer, setActiveMiniDrawer] = useState<MiniDrawerKind>('none');
  const [sharedMemoryBus, setSharedMemoryBus] = useState<Record<string, any>>({
    last_event: 'USER_CLICK_GENERATE_DASHBOARD',
    intent: 'create_cyber_analytics_card',
    co_agent_review: 'PASS_WITH_99.2%_CONFIDENCE',
    dom_hydration_status: 'READY',
  });

  // 大模型设置表单：不再内置明文默认值，打开设置抽屉时由 GET /settings/llm 回填
  const [llmForm, setLlmForm] = useState({ api_key: '', api_base: '', model: '', key_hint: '' });
  const [llmMsg, setLlmMsg] = useState<string>('');
  // 管理令牌仅存 sessionStorage，随请求头 X-Admin-Token 发送（T43 登录态）
  const [adminToken, setAdminTokenState] = useState<string>(() => sessionStorage.getItem('aigent_admin_token') ?? '');

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
  const [wsRetryCount, setWsRetryCount] = useState<number>(0); // T42：重连中第 N 次
  const [wsReconnectKey, setWsReconnectKey] = useState<number>(0); // T43：令牌变更重建 WS
  const prefersReduced = usePrefersReducedMotion(); // T45：系统减少动态偏好
  const [narrowPanel, setNarrowPanel] = useState<'none' | 'library' | 'inspector'>('none'); // T45：窄屏抽屉
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

  const handleAdminTokenChange = (value: string) => {
    setAdminTokenState(value);
    setAdminToken(value); // config.ts：sessionStorage 持久化（T11/T43）
    setWsReconnectKey((k) => k + 1); // 令牌变更 → 携带新 ?token= 重建 WS
  };

  // T43：REST 401 → 自动打开设置抽屉让用户填写令牌
  useEffect(() => {
    const onUnauthorized = () => setActiveMiniDrawer('settings');
    window.addEventListener('aigent:unauthorized', onUnauthorized);
    return () => window.removeEventListener('aigent:unauthorized', onUnauthorized);
  }, []);

  // ======================= T32(32c)：多工作流切换器 =======================
  const refreshWorkflows = useCallback(async () => {
    try {
      setWorkflows(await workflowApi.listWorkflows());
    } catch {
      // 后端未启动（离线仿真）时静默
    }
  }, []);

  const applySnapshotTopology = useCallback((snap: { nodes?: WorkflowNode[]; edges?: NeuralEdge[]; terminal_logs?: string[]; workflow_id?: string }) => {
    if (snap.workflow_id) setActiveWorkflowId(snap.workflow_id);
    setNodes(snap.nodes ?? []);
    setEdges(snap.edges ?? []);
    if (snap.terminal_logs) setTerminalLogs(snap.terminal_logs);
  }, []);

  const activateWorkflow = useCallback(
    async (id: string) => {
      if (!id || id === activeWorkflowId) return;
      try {
        const snap = await workflowApi.activateWorkflow(id);
        applySnapshotTopology(snap);
        pushLog(`[Workflow] 已切换到工作流 ${snap.workflow_id ?? id}`);
        void refreshWorkflows();
      } catch (err) {
        pushLog(`[Error] 切换工作流失败: ${String(err)}`);
      }
    },
    [activeWorkflowId, applySnapshotTopology, pushLog, refreshWorkflows]
  );

  const createWorkflow = useCallback(async () => {
    const name = window.prompt('新工作流名称', '新工作流');
    if (!name) return;
    try {
      const wf = await workflowApi.createWorkflow(name);
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
      await workflowApi.batchPositions(positions);
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
      const body = await workflowApi.aiSuggest(prompt);
      pushLog(`[AI-Suggest] 已新增 ${body.added_nodes} 节点 / ${body.added_edges} 连线`);
      const snap = await workflowApi.getSnapshot();
      setNodes(snap.nodes);
      setEdges(snap.edges);
    } catch (err) {
      pushLog(`[Error] AI 建议失败: ${String(err)}`);
    }
  }, [pushLog]);

  const { linkingSourceId, handleNodeShiftClick, persistNodePosition } = useSynapseLinker(
    API_BASE,
    (newEdge) => {
      setEdges((prev) => [...prev, newEdge]);
      pushUndo({ kind: 'add_edge', edge: newEdge });
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

  // ==================== WebSocket 实时遥测（T40：效果体已迁至 useWorkflowSocket） ====================
  useWorkflowSocket({
    onSnapshot: (data) => {
      if (data.workflow_id) setActiveWorkflowId(data.workflow_id);
      setProjectStatus(data.project_status);
      // 拖拽中的节点沿用本地坐标，避免被整张快照拽走
      setNodes(
        (data.nodes as WorkflowNode[]).map((n) => {
          if (draggingRef.current === n.id) {
            const local = nodesRef.current.find((x) => x.id === n.id);
            return local ? { ...n, position: local.position } : n;
          }
          return n;
        })
      );
      setEdges(data.edges);
      setTerminalLogs(data.terminal_logs);
    },
    onTelemetry: (data) => {
      setProjectStatus(data.project_status);
      setCpuSeries(data.cpu_history);
      setMemSeries(data.memory_history);
      setRadar(data.radar_metrics);
      setEcgSeries(data.ecg_waveform ?? []); // T27：真实 DAG 轮延迟序列
    },
    onNodeUpdate: (data) => {
      const n = data.node;
      setNodes((prev) =>
        prev.map((x) =>
          x.id === n.id
            ? { ...x, ...n, position: draggingRef.current === n.id ? x.position : n.position }
            : x
        )
      );
      // T31：最终态到达，结束该节点的流式显示
      setStreamInfo((prev) => (prev && prev.nodeId === n.id ? null : prev));
      if (data.shared_memory_bus) setSharedMemoryBus(data.shared_memory_bus);
    },
    onNodeStream: (data) => {
      // T31：LLM 增量输出（node_id + delta），右侧面板实时累积显示
      const { node_id: streamNodeId, delta } = data;
      setStreamInfo((prev) =>
        prev && prev.nodeId === streamNodeId
          ? { nodeId: streamNodeId, text: prev.text + delta }
          : { nodeId: streamNodeId, text: delta }
      );
    },
    onTerminalLog: (data) => setTerminalLogs(data.logs),
    onConnectionChange: (connected) => {
      setWsConnected(connected);
      if (connected) setWsRetryCount(0);
    },
    onReconnecting: (attempt) => {
      setWsRetryCount(attempt);
      if (attempt === 1) emitToast('与后端断开，正在重连…', 'info');
    },
    onSimulateTelemetry: () => {
      setCpuSeries((prev) => [...prev.slice(1), Math.round(28 + Math.random() * 52)]);
      setMemSeries((prev) => [...prev.slice(1), +(60 + Math.random() * 9).toFixed(1)]);
    },
    draggingRef,
    nodesRef,
    projectStatusRef,
    wsConnectedRef,
    reconnectKey: wsReconnectKey,
  });

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
      await workflowApi.control(action);
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
        const created: WorkflowNode = await workflowApi.addNode({
          component_id: item.id,
          x: 455,
          y: randomY,
          connect_from: selectedNodeId || null,
        });
        setNodes((prev) =>
          prev.some((n) => n.id === created.id)
            ? prev.map((n) => (n.id === created.id ? created : n))
            : [...prev, created]
        );
        pushUndo({ kind: 'add_node', node: created });
        setSelectedNodeId(created.id);
        pushLog(`[Topology] 已挂载神经元节点: ${item.label}`);
      } catch (err) {
        pushLog(`[Error] 添加节点失败: ${String(err)}`);
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

  // ==================== T44：框选 / 缩放平移 / 命令栈状态 ====================
  const [selectionSet, setSelectionSet] = useState<Set<string>>(new Set());
  const [selectionRect, setSelectionRect] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [view, setView] = useState<{ zoom: number; panX: number; panY: number }>({ zoom: 1, panX: 0, panY: 0 });
  const mainRef = useRef<HTMLDivElement | null>(null);
  const boxStartRef = useRef<{ x: number; y: number } | null>(null);
  const panStateRef = useRef<{ lastX: number; lastY: number } | null>(null);

  // ==================== T44：撤销 / 重做（命令栈，经后端幂等 API 反向执行） ====================
  const undoStackRef = useRef<TopoCommand[]>([]);
  const redoStackRef = useRef<TopoCommand[]>([]);
  const [historySize, setHistorySize] = useState<{ undo: number; redo: number }>({ undo: 0, redo: 0 });

  const syncHistorySize = useCallback(() => {
    setHistorySize({ undo: undoStackRef.current.length, redo: redoStackRef.current.length });
  }, []);

  const pushUndo = useCallback(
    (cmd: TopoCommand) => {
      undoStackRef.current = [...undoStackRef.current.slice(-49), cmd];
      redoStackRef.current = [];
      syncHistorySize();
    },
    [syncHistorySize]
  );

  const refreshSnapshotQuiet = useCallback(async () => {
    try {
      const snap = await workflowApi.getSnapshot();
      setNodes(snap.nodes);
      setEdges(snap.edges);
    } catch {
      // 离线时保留本地状态
    }
  }, []);

  const applyUndo = useCallback(async () => {
    const cmd = undoStackRef.current.pop();
    if (!cmd) return;
    try {
      if (cmd.kind === 'add_node') {
        await workflowApi.deleteNode(cmd.node.id);
      } else if (cmd.kind === 'del_node') {
        await workflowApi.addNode({ component_id: cmd.node.type, x: cmd.node.position.x, y: cmd.node.position.y, connect_from: null });
        for (const e of cmd.edges) {
          try {
            await workflowApi.addEdge(e.source, e.target);
          } catch {
            // 连线可能已存在（409）或端点为本地仿真节点，忽略
          }
        }
      } else if (cmd.kind === 'add_edge') {
        await workflowApi.deleteEdge(cmd.edge.id);
      } else {
        await workflowApi.addEdge(cmd.edge.source, cmd.edge.target);
      }
      redoStackRef.current = [...redoStackRef.current, cmd];
      syncHistorySize();
      await refreshSnapshotQuiet();
      pushLog('[History] 已撤销上一步拓扑操作');
    } catch (err) {
      undoStackRef.current = [...undoStackRef.current, cmd]; // 失败回滚栈
      pushLog(`[Error] 撤销失败: ${String(err)}`);
    }
  }, [pushLog, refreshSnapshotQuiet, syncHistorySize]);

  const applyRedo = useCallback(async () => {
    const cmd = redoStackRef.current.pop();
    if (!cmd) return;
    try {
      if (cmd.kind === 'add_node') {
        const created = await workflowApi.addNode({ component_id: cmd.node.type, x: cmd.node.position.x, y: cmd.node.position.y, connect_from: null });
        void created;
      } else if (cmd.kind === 'del_node') {
        await workflowApi.deleteNode(cmd.node.id);
      } else if (cmd.kind === 'add_edge') {
        await workflowApi.addEdge(cmd.edge.source, cmd.edge.target);
      } else {
        await workflowApi.deleteEdge(cmd.edge.id);
      }
      undoStackRef.current = [...undoStackRef.current, cmd];
      syncHistorySize();
      await refreshSnapshotQuiet();
      pushLog('[History] 已重做拓扑操作');
    } catch (err) {
      redoStackRef.current = [...redoStackRef.current, cmd];
      pushLog(`[Error] 重做失败: ${String(err)}`);
    }
  }, [pushLog, refreshSnapshotQuiet, syncHistorySize]);

  // ==================== 节点与连线删除（拓扑抽屉 / 检视器 / Delete 键共用） ====================
  const handleDeleteNode = useCallback(
    async (nodeId: string) => {
      if (!nodeId) return;
      try {
        await workflowApi.deleteNode(nodeId);
        const removedNode = nodesRef.current.find((n) => n.id === nodeId);
        const removedEdges = edges.filter((e) => e.source === nodeId || e.target === nodeId);
        if (removedNode) {
          pushUndo({ kind: 'del_node', node: removedNode, edges: removedEdges });
        }
        setNodes((prev) => prev.filter((n) => n.id !== nodeId));
        setEdges((prev) => prev.filter((e) => e.source !== nodeId && e.target !== nodeId));
        setSelectedNodeId((prev) => (prev === nodeId ? '' : prev));
        setSelectionSet(new Set());
        pushLog(`[Topology] 已删除节点 ${nodeId}`);
      } catch (err) {
        pushLog(`[Error] ${String(err)}`);
      }
    },
    [edges, pushLog]
  );

  const handleDeleteEdge = useCallback(
    async (edgeId: string) => {
      try {
        await workflowApi.deleteEdge(edgeId);
        const removed = edges.find((e) => e.id === edgeId);
        if (removed) pushUndo({ kind: 'del_edge', edge: removed });
        setEdges((prev) => prev.filter((e) => e.id !== edgeId));
        pushLog(`[Synapse] 已断开连线 ${edgeId}`);
      } catch (err) {
        pushLog(`[Error] ${String(err)}`);
      }
    },
    [edges, pushLog]
  );

  // ==================== T44：键盘（Delete / Ctrl+Z / Ctrl+Y）与原生滚轮缩放 ====================
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const inEditor = tag === 'INPUT' || tag === 'TEXTAREA';
      if ((e.ctrlKey || e.metaKey) && !inEditor && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) void applyRedo();
        else void applyUndo();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && !inEditor && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        void applyRedo();
        return;
      }
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      if (inEditor) return;
      if (selectionSet.size > 0) {
        if (window.confirm(`确认删除选中的 ${selectionSet.size} 个节点？`)) {
          selectionSet.forEach((id) => void handleDeleteNode(id));
        }
        return;
      }
      if (e.key === 'Delete' && selectedNodeId) {
        if (window.confirm(`确认删除节点 ${selectedNodeId}？`)) {
          handleDeleteNode(selectedNodeId);
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedNodeId, selectionSet, handleDeleteNode, applyUndo, applyRedo]);

  // 原生 wheel 监听（React 的 onWheel 为 passive，无法 preventDefault 阻止浏览器缩放）
  useEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      setView((v) => {
        const zoom = Math.min(2.5, Math.max(0.4, v.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
        return { ...v, zoom };
      });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  // ==================== 拓扑抽屉：最近运行记录 ====================
  const fetchRunHistory = useCallback(async () => {
    try {
      setRunHistory(await workflowApi.fetchRunHistory());
    } catch {
      // 离线时保留上次记录
    }
  }, []);

  useEffect(() => {
    if (activeMiniDrawer === 'topology' && wsConnected) {
      fetchRunHistory();
    }
  }, [activeMiniDrawer, wsConnected, fetchRunHistory]);

  // ==================== 设置抽屉：大模型配置读取与更新 ====================
  const fetchLlmSettings = useCallback(async () => {
    try {
      const data = await workflowApi.fetchLlmSettings();
      // api_key 留空表示不修改；其余由后端回填
      setLlmForm({
        api_key: '',
        api_base: data.api_base ?? '',
        model: data.model ?? '',
        key_hint: data.key_hint ?? '',
      });
      setLlmMsg(`当前密钥: ${data.key_hint || '未设置'} | has_key: ${data.has_key}`);
    } catch (err) {
      setLlmMsg(`读取失败: ${String(err)}`);
    }
  }, []);

  useEffect(() => {
    if (activeMiniDrawer === 'settings' && wsConnected) {
      fetchLlmSettings();
    }
  }, [activeMiniDrawer, wsConnected, fetchLlmSettings]);

  const handleUpdateLlmSettings = async () => {
    try {
      await workflowApi.updateLlmSettings({
        api_key: llmForm.api_key,
        api_base: llmForm.api_base,
        model: llmForm.model,
      });
      setLlmMsg('已更新');
      pushLog('[Settings] 已更新智能体大模型驱动内核');
      fetchLlmSettings();
    } catch (err) {
      const detail = String(err).replace(/^Error:\s*/, '');
      setLlmMsg(`更新失败: ${detail}`);
      pushLog(`[Error] 更新模型配置失败: ${detail}`);
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLElement>) => {
    if (!draggingNodeId) return;
    const rect = e.currentTarget.getBoundingClientRect();
    // T44：视图缩放下的拖拽（位移换算回画布坐标）
    const nextX = Math.max(10, Math.min((rect.width - 230) / view.zoom, (e.clientX - rect.left) / view.zoom - dragOffsetRef.current.x));
    const nextY = Math.max(10, Math.min((rect.height - 150) / view.zoom, (e.clientY - rect.top) / view.zoom - dragOffsetRef.current.y));
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
            {/* T44：撤销 / 重做 */}
            <button
              type="button"
              aria-label="撤销"
              onClick={() => void applyUndo()}
              disabled={historySize.undo === 0}
              title="撤销 (Ctrl+Z)"
              className="px-2 py-1 rounded-md bg-slate-900/80 border border-slate-600/70 text-[11px] text-slate-200 font-mono hover:border-slate-300 disabled:opacity-40 disabled:hover:border-slate-600/70 transition"
            >
              ↶
            </button>
            <button
              type="button"
              aria-label="重做"
              onClick={() => void applyRedo()}
              disabled={historySize.redo === 0}
              title="重做 (Ctrl+Y)"
              className="px-2 py-1 rounded-md bg-slate-900/80 border border-slate-600/70 text-[11px] text-slate-200 font-mono hover:border-slate-300 disabled:opacity-40 disabled:hover:border-slate-600/70 transition"
            >
              ↷
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

        {/* T45：窄屏抽屉切换（lg 以下显示） */}
        <div className="flex items-center gap-1 lg:hidden">
          <button type="button" aria-label="切换算子库" onClick={() => setNarrowPanel((k) => (k === 'library' ? 'none' : 'library'))} className="px-2 py-1 rounded-md bg-slate-900/80 border border-slate-600/70 text-[11px] text-cyan-300 font-mono">库</button>
          <button type="button" aria-label="切换属性面板" onClick={() => setNarrowPanel((k) => (k === 'inspector' ? 'none' : 'inspector'))} className="px-2 py-1 rounded-md bg-slate-900/80 border border-slate-600/70 text-[11px] text-cyan-300 font-mono">属性</button>
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

          {/* 后端连接指示灯：绿点=已连接后端；黄点=重连中；灰点=本地仿真（T42 状态条） */}
          <div
            className="pl-3 text-xs text-slate-300 flex items-center space-x-1.5"
            title={wsConnected ? `WS: ${WS_URL}` : `等待后端 ${WS_URL}`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                wsConnected
                  ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.95)]'
                  : wsRetryCount > 0
                  ? 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.9)]'
                  : 'bg-slate-500'
              }`}
            />
            <span
              className={
                wsConnected ? 'text-emerald-300' : wsRetryCount > 0 ? 'text-amber-300' : 'text-slate-400'
              }
            >
              {wsConnected ? '已连接后端' : wsRetryCount > 0 ? `重连中 第 ${wsRetryCount} 次` : '本地仿真'}
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
              aria-label="清空侧栏"
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
              aria-label="共享记忆总线"
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
              aria-label="拓扑与运行记录"
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
              aria-label="打开沙盒"
              onClick={() => setShowSandboxModal(true)}
              className="w-8 h-8 rounded-lg hover:bg-slate-800/60 flex items-center justify-center text-slate-400 hover:text-cyan-300"
            >
              <Share2 className="w-4 h-4" />
            </button>
            <button
              aria-label="导出工程 ZIP"
              onClick={() => window.open(`${API_BASE}/publish/export-zip`, '_blank')}
              className="w-8 h-8 rounded-lg hover:bg-slate-800/60 flex items-center justify-center text-slate-400 hover:text-emerald-300"
            >
              <FileCode className="w-4 h-4" />
            </button>
            <button
              aria-label="时间旅行控制台"
              onClick={() => setShowSandboxModal(true)}
              className="w-8 h-8 rounded-lg hover:bg-cyan-950/60 flex items-center justify-center text-cyan-400"
            >
              <Sparkles className="w-4 h-4" />
            </button>
          </div>
          <div className="flex flex-col items-center space-y-4">
            <button
              aria-label="打开沙盒与断点"
              onClick={() => setShowSandboxModal(true)}
              className="w-8 h-8 rounded-lg hover:bg-slate-800/60 flex items-center justify-center text-slate-400 hover:text-emerald-300"
            >
              <Clock className="w-4 h-4" />
            </button>
            <button
              aria-label="大模型设置"
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

        {/* 2.1.5 迷你抽屉浮层（T40：已拆分至 components/MiniDrawer） */}
        <MiniDrawer
          kind={activeMiniDrawer}
          onClose={() => setActiveMiniDrawer('none')}
          wsConnected={wsConnected}
          sharedMemoryBus={sharedMemoryBus}
          nodes={nodes}
          edges={edges}
          runHistory={runHistory}
          onDeleteNode={(id) => void handleDeleteNode(id)}
          onDeleteEdge={(id) => void handleDeleteEdge(id)}
          onRefreshRunHistory={fetchRunHistory}
          llmForm={llmForm}
          onLlmFormChange={(patch) => setLlmForm((f) => ({ ...f, ...patch }))}
          llmMsg={llmMsg}
          adminToken={adminToken}
          onAdminTokenChange={handleAdminTokenChange}
          onSaveLlm={() => void handleUpdateLlmSettings()}
        />

        {/* 2.2 左侧算子与组件库面板（T40：已拆分至 components/ComponentLibrary） */}
        <ComponentLibrary
          search={sidebarSearch}
          onSearchChange={setSidebarSearch}
          onAddItem={(item) => void handleAddComponentNode(item)}
          onAiSuggest={() => void handleAiSuggest()}
        />

        {/* 2.3 中央加色混合生物发光神经元画布（T44：框选 / 中键平移 / Ctrl+滚轮缩放） */}
        <main
          ref={mainRef}
          onMouseMove={(e) => {
            // 框选中：更新选区矩形
            if (boxStartRef.current) {
              const rect = e.currentTarget.getBoundingClientRect();
              setSelectionRect({
                x1: boxStartRef.current.x,
                y1: boxStartRef.current.y,
                x2: (e.clientX - rect.left - view.panX) / view.zoom,
                y2: (e.clientY - rect.top - view.panY) / view.zoom,
              });
              return;
            }
            // 中键平移
            if (panStateRef.current) {
              const dx = e.clientX - panStateRef.current.lastX;
              const dy = e.clientY - panStateRef.current.lastY;
              panStateRef.current = { lastX: e.clientX, lastY: e.clientY };
              setView((v) => ({ ...v, panX: v.panX + dx, panY: v.panY + dy }));
              return;
            }
            handleCanvasMouseMove(e);
          }}
          onMouseDown={(e) => {
            if (e.target !== e.currentTarget) return;
            if (e.button === 1) {
              // 中键：平移
              e.preventDefault();
              panStateRef.current = { lastX: e.clientX, lastY: e.clientY };
              return;
            }
            if (e.button === 0) {
              // 左键空白处：开始框选（画布坐标 = (client - rect - pan) / zoom）
              const rect = e.currentTarget.getBoundingClientRect();
              boxStartRef.current = {
                x: (e.clientX - rect.left - view.panX) / view.zoom,
                y: (e.clientY - rect.top - view.panY) / view.zoom,
              };
              setSelectionRect({ x1: boxStartRef.current.x, y1: boxStartRef.current.y, x2: boxStartRef.current.x, y2: boxStartRef.current.y });
              setSelectionSet(new Set());
            }
          }}
          onMouseUp={() => {
            if (panStateRef.current) {
              panStateRef.current = null;
              return;
            }
            if (boxStartRef.current && selectionRect) {
              const minX = Math.min(selectionRect.x1, selectionRect.x2);
              const maxX = Math.max(selectionRect.x1, selectionRect.x2);
              const minY = Math.min(selectionRect.y1, selectionRect.y2);
              const maxY = Math.max(selectionRect.y1, selectionRect.y2);
              if (Math.abs(maxX - minX) > 8 && Math.abs(maxY - minY) > 8) {
                const hits = nodesRef.current
                  .filter((n) => {
                    const nx = n.position.x;
                    const ny = n.position.y;
                    return nx + 195 >= minX && nx <= maxX && ny + 120 >= minY && ny <= maxY;
                  })
                  .map((n) => n.id);
                setSelectionSet(new Set(hits));
                if (hits.length > 0) pushLog(`[Select] 框选 ${hits.length} 个节点`);
              }
              boxStartRef.current = null;
              setSelectionRect(null);
              return;
            }
            handleCanvasMouseUp();
          }}
          onContextMenu={(e) => e.preventDefault()}
          className="flex-1 relative overflow-hidden bg-[#080c17]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        >
          {/* T44：缩放平移变换层（画布引擎与节点卡同步变换） */}
          <div
            className="absolute inset-0"
            style={{ transform: `translate(${view.panX}px, ${view.panY}px) scale(${view.zoom})`, transformOrigin: '0 0' }}
          >
          {/* 60FPS 加色混合生物神经元 + 多股交织突触彗星脉冲引擎 */}
          <BioluminescentCanvas
            isRunning={projectStatus === '运行中' && !prefersReduced}
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

          {/* 画布神经元节点渲染层（T40：卡片已拆分至 components/NodeCard） */}
          {nodes
            .filter(
              (n) =>
                !globalSearch ||
                n.title.toLowerCase().includes(globalSearch.toLowerCase()) ||
                n.subtitle.toLowerCase().includes(globalSearch.toLowerCase())
            )
            .map((node) => (
              <NodeCard
                key={node.id}
                node={node}
                isSelected={node.id === selectedNodeId}
                isInSelection={selectionSet.has(node.id)}
                isLinkSource={node.id === linkingSourceId}
                isRunning={projectStatus === '运行中' && !prefersReduced}
                ecgSeries={ecgSeries}
                onOpenSandbox={() => setShowSandboxModal(true)}
                onNodeMouseDown={(e, nd) => {
                  e.stopPropagation();
                  if (e.shiftKey) {
                    handleNodeShiftClick(nd.id);
                    return;
                  }
                  setSelectionSet(new Set());
                  setSelectedNodeId(nd.id);
                  setDraggingNodeId(nd.id);
                  dragOffsetRef.current = {
                    x: (e.clientX - e.currentTarget.getBoundingClientRect().left) / view.zoom,
                    y: (e.clientY - e.currentTarget.getBoundingClientRect().top) / view.zoom,
                  };
                }}
              />
            ))}
          </div>

          {/* T44：框选矩形（画布坐标 → 屏幕坐标） */}
          {selectionRect && (
            <div
              className="absolute border border-cyan-400/80 bg-cyan-400/10 pointer-events-none z-30"
              style={{
                left: Math.min(selectionRect.x1, selectionRect.x2) * view.zoom + view.panX,
                top: Math.min(selectionRect.y1, selectionRect.y2) * view.zoom + view.panY,
                width: Math.abs(selectionRect.x2 - selectionRect.x1) * view.zoom,
                height: Math.abs(selectionRect.y2 - selectionRect.y1) * view.zoom,
              }}
            />
          )}
        </main>

        {/* 2.4 右侧属性配置、五维扫描雷达、JSON 配置区与 AI 终端 */}
        <aside
          className={`${narrowPanel === 'inspector' ? 'fixed inset-y-0 right-0 z-50 shadow-2xl' : 'hidden'} lg:flex w-[310px] bg-[#0d1322]/95 border-l border-slate-800/80 flex-col justify-between p-3 space-y-3 z-20 overflow-y-auto`}>
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
              isRunning={projectStatus === '运行中' && !prefersReduced}
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
                  if (wsConnected && selectedNode) {
                    try {
                      const updated: WorkflowNode = await workflowApi.putNodeConfig(
                        selectedNode.id,
                        parsed
                      );
                      setNodes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
                      pushLog(`[Inspector] 已应用节点 ${selectedNode.title} 配置`);
                    } catch (err) {
                      pushLog(`[Error] 热更新失败: ${String(err).replace(/^Error:\s*/, '')}，保持原值`);
                    }
                    return;
                  }
                  if (!selectedNode) return;
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
            {/* T40：终端面板已拆分至 components/TerminalLog（分级着色 classifyLogLine） */}
            <TerminalLog logs={terminalLogs} />
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
            const snap = await workflowApi.getSnapshot();
            setNodes(snap.nodes);
            setEdges(snap.edges);
            setTerminalLogs(snap.terminal_logs);
            setProjectStatus(snap.project_status);
          } catch {
            // 离线时保留本地状态
          }
        }}
      />
    </div>
  );
}
