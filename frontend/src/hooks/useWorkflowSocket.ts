// frontend/src/hooks/useWorkflowSocket.ts —— T40：WS 实时遥测（自 Workbench 原样迁出）
// 保留：wsLoopGeneration 代际锁（Vite HMR 遗留循环防护）、指数退避重连、本地仿真回退内核。
import { useEffect } from 'react';
import { buildWsUrl } from '../config';
import type { NeuralEdge, ProjectStatus, WorkflowNode } from '../types';

// WS 重连循环的代际锁：同一页面只允许最新挂载的 effect 循环持有连接。
// Vite HMR（React Refresh）可能遗留 detached fiber 的旧循环，旧循环在
// 下次触发时发现代际不符即静默退出，避免出现双连接与指示灯错乱。
let wsLoopGeneration = 0;
let moduleWs: WebSocket | null = null;

export interface WorkflowSocketHandlers {
  onSnapshot: (data: {
    workflow_id?: string;
    project_status: ProjectStatus;
    nodes: WorkflowNode[];
    edges: NeuralEdge[];
    terminal_logs: string[];
  }) => void;
  onTelemetry: (data: {
    project_status: ProjectStatus;
    cpu_history: number[];
    memory_history: number[];
    radar_metrics: { radar_perception: number; responsiveness: number; accuracy: number; concurrency: number; stability: number };
    ecg_waveform?: number[];
  }) => void;
  onNodeUpdate: (data: { node: WorkflowNode; shared_memory_bus?: Record<string, any> }) => void;
  onNodeStream: (data: { node_id: string; delta: string }) => void;
  onTerminalLog: (data: { logs: string[] }) => void;
  onConnectionChange: (connected: boolean) => void;
  /** T42：每次调度重连时回调（attempt 从 1 开始），驱动「重连中 第 N 次」状态条 */
  onReconnecting?: (attempt: number) => void;
  /** 本地仿真回退：每 450ms 驱动一次 CPU/内存曲线（仅离线时） */
  onSimulateTelemetry: () => void;
  /** 鉴别「拖拽中」节点与最新节点坐标（快照合并用） */
  draggingRef: React.MutableRefObject<string | null>;
  nodesRef: React.MutableRefObject<WorkflowNode[]>;
  projectStatusRef: React.MutableRefObject<ProjectStatus>;
  wsConnectedRef: React.MutableRefObject<boolean>;
  /** T43：令牌变更时递增以强制重建 WS 连接（新连接携带新 ?token=） */
  reconnectKey?: number;
}

export function useWorkflowSocket(handlers: WorkflowSocketHandlers): void {
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
        handlers.wsConnectedRef.current = true;
        handlers.onConnectionChange(true);
      };
      ws.onclose = () => {
        handlers.wsConnectedRef.current = false;
        handlers.onConnectionChange(false);
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
          handlers.onSnapshot(msg.data);
        } else if (msg.event === 'telemetry_tick') {
          handlers.onTelemetry(msg.data);
        } else if (msg.event === 'node_update') {
          handlers.onNodeUpdate(msg.data);
        } else if (msg.event === 'node_stream') {
          // T31：LLM 增量输出（node_id + delta）
          handlers.onNodeStream(msg.data);
        } else if (msg.event === 'terminal_log') {
          handlers.onTerminalLog(msg.data);
        }
      };
    };

    const scheduleReconnect = () => {
      if (disposed || generation !== wsLoopGeneration) return;
      const delay = Math.min(15000, 1000 * Math.pow(2, retry));
      retry += 1;
      handlers.onReconnecting?.(retry);
      reconnectTimer = window.setTimeout(connect, delay);
    };

    connect();

    // 本地仿真回退内核：后端未连接时驱动 CPU/内存曲线（读取 ref 避免闭包过期）
    const fallbackTimer = window.setInterval(() => {
      if (handlers.wsConnectedRef.current || handlers.projectStatusRef.current === '已暂停') return;
      handlers.onSimulateTelemetry();
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
    // 生命周期型 effect：挂载与 reconnectKey 变化时重建（快照合并经 refs 读取最新态）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handlers.reconnectKey ?? 0]);
}
