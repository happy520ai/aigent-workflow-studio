// frontend/src/components/Toast.tsx —— T42：全局轻量 toast（模块级 pub/sub，成功/失败/降级）
import React, { useEffect, useState } from 'react';

export type ToastKind = 'success' | 'error' | 'info';

export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}

type Listener = (toasts: ToastItem[]) => void;

let toasts: ToastItem[] = [];
let nextId = 1;
const listeners = new Set<Listener>();

function notify() {
  for (const l of listeners) l([...toasts]);
}

export function emitToast(text: string, kind: ToastKind = 'info', ttlMs = 4000): void {
  const item: ToastItem = { id: nextId++, kind, text };
  toasts = [...toasts.slice(-4), item]; // 最多同时 5 条
  notify();
  window.setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== item.id);
    notify();
  }, ttlMs);
}

const KIND_STYLE: Record<ToastKind, string> = {
  success: 'bg-emerald-500/15 border-emerald-400/60 text-emerald-200',
  error: 'bg-rose-500/15 border-rose-400/60 text-rose-200',
  info: 'bg-cyan-500/15 border-cyan-400/60 text-cyan-200',
};

export const ToastHost: React.FC = () => {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => {
    const listener: Listener = (t) => setItems(t);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  if (items.length === 0) return null;
  return (
    <div
      className="fixed top-[68px] right-4 z-[100] flex flex-col gap-2 pointer-events-none"
      role="status"
      aria-live="polite"
    >
      {items.map((t) => (
        <div
          key={t.id}
          className={`px-3 py-2 rounded-lg border backdrop-blur-md text-xs font-medium max-w-sm shadow-lg ${KIND_STYLE[t.kind]}`}
        >
          {t.text}
        </div>
      ))}
    </div>
  );
};
