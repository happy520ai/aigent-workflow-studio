// frontend/src/components/ErrorBoundary.tsx —— T42：顶层错误边界（渲染异常兜底，不白屏）
import React from 'react';

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] 渲染异常:', error, info.componentStack);
  }

  render(): React.ReactNode {
    if (this.state.error) {
      return (
        <div className="w-screen h-screen bg-[#070a12] text-slate-100 flex items-center justify-center p-8 font-sans">
          <div className="max-w-lg w-full rounded-xl border border-rose-500/40 bg-rose-500/10 p-6">
            <div className="text-sm font-bold text-rose-300 mb-2">界面渲染异常，已停止扩散</div>
            <pre className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-all max-h-48 overflow-y-auto mb-4">
              {this.state.error.message}
            </pre>
            <button
              onClick={() => {
                this.setState({ error: null });
                window.location.reload();
              }}
              className="px-3 py-1.5 rounded-md bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 text-xs font-semibold hover:bg-cyan-500/30"
            >
              重新加载工作台
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
