// frontend/src/hooks/useWorkflowBackend.ts
import { useRef } from 'react';

export interface WorkflowSnapshotMsg {
  project_status: string;
  nodes: any[];
  edges: any[];
  terminal_logs: string[];
  [key: string]: any;
}

export interface TelemetryTickMsg {
  project_status: string;
  cpu_history: number[];
  memory_history: number[];
  ecg_waveform: number[];
  radar_metrics: Record<string, number>;
  edges: any[];
  sandbox_html?: string;
  shared_memory_bus?: Record<string, any>;
  [key: string]: any;
}

interface Handlers {
  onSnapshot?: (data: WorkflowSnapshotMsg) => void;
  onTelemetryTick?: (data: TelemetryTickMsg) => void;
  onTerminalLog?: (logs: string[]) => void;
  onNodeUpdate?: (data: Record<string, any>) => void;
}

/**
 * WebSocket 实时遥测与控制指令 Hook：
 * 与 FastAPI 后端 /ws/telemetry 建立双向长连接，将 workflow_snapshot /
 * telemetry_tick / terminal_log / node_update 事件分发至对应回调。
 */
export function useWorkflowBackend(
  wsUrl = 'ws://localhost:8000/ws/telemetry',
  handlers: Handlers = {}
) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const connect = () => {
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      return null;
    }
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.event === 'workflow_snapshot') {
          handlersRef.current.onSnapshot?.(msg.data);
        } else if (msg.event === 'telemetry_tick') {
          handlersRef.current.onTelemetryTick?.(msg.data);
        } else if (msg.event === 'terminal_log') {
          handlersRef.current.onTerminalLog?.(msg.data?.logs ?? []);
        } else if (msg.event === 'node_update') {
          handlersRef.current.onNodeUpdate?.(msg.data);
        }
      } catch {
        // 忽略无法解析的报文
      }
    };
    return ws;
  };

  const sendControl = async (action: 'run' | 'pause' | 'debug' | 'reset', apiBase = 'http://localhost:8000/api/v1') => {
    try {
      await fetch(`${apiBase}/workflow/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
    } catch {
      // 离线仿真模式下由调用方接管状态
    }
  };

  return { connect, sendControl };
}
