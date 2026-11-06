// frontend/src/hooks/useWorkflowSocket.test.tsx —— T50：重连指数退避（fake timers）
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useWorkflowSocket } from './useWorkflowSocket';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: ((...a: any[]) => void) | null = null;
  onclose: ((...a: any[]) => void) | null = null;
  onerror: ((...a: any[]) => void) | null = null;
  onmessage: ((...a: any[]) => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  close() {
    this.closed = true;
  }
}

const noop = () => {};

function makeHandlers() {
  return {
    onSnapshot: noop,
    onTelemetry: noop,
    onNodeUpdate: noop,
    onNodeStream: noop,
    onTerminalLog: noop,
    onConnectionChange: noop,
    onSimulateTelemetry: noop,
    draggingRef: { current: null },
    nodesRef: { current: [] },
    projectStatusRef: { current: '运行中' as const },
    wsConnectedRef: { current: false },
  };
}

describe('useWorkflowSocket 重连退避', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    (globalThis as any).window.WebSocket = FakeWebSocket as any;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('断线后按 1s/2s/4s 指数退避重连；重连成功后重置回 1s', () => {
    const { unmount } = renderHook(() => useWorkflowSocket(makeHandlers()));
    expect(FakeWebSocket.instances).toHaveLength(1);

    // 第 1 次断开 → 1s 后重连
    act(() => {
      FakeWebSocket.instances[0].onclose?.();
    });
    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(FakeWebSocket.instances).toHaveLength(2);

    // 第 2 次断开 → 2s 后重连
    act(() => {
      FakeWebSocket.instances[1].onclose?.();
    });
    act(() => {
      vi.advanceTimersByTime(1999);
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(FakeWebSocket.instances).toHaveLength(3);

    // 第 3 次断开 → 4s 后重连
    act(() => {
      FakeWebSocket.instances[2].onclose?.();
    });
    act(() => {
      vi.advanceTimersByTime(3999);
    });
    expect(FakeWebSocket.instances).toHaveLength(3);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(FakeWebSocket.instances).toHaveLength(4);

    // 连接成功后 retry 清零：再断开 → 回到 1s
    act(() => {
      FakeWebSocket.instances[3].onopen?.();
      FakeWebSocket.instances[3].onclose?.();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeWebSocket.instances).toHaveLength(5);
    unmount();
  });

  it('卸载后不再重连（代际锁与 disposed 生效）', () => {
    const { unmount } = renderHook(() => useWorkflowSocket(makeHandlers()));
    const first = FakeWebSocket.instances[0];
    unmount();
    expect(first.closed).toBe(true);
    act(() => {
      first.onclose?.();
      vi.advanceTimersByTime(60000);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
