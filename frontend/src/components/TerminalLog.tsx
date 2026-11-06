// frontend/src/components/TerminalLog.tsx —— T40：AI 终端日志（分级着色，原样迁出）
import React from 'react';

export const classifyLogLine = (line: string): string => {
  const isError = line.startsWith('[Error]') || line.startsWith('[Warn]');
  const isSystem =
    line.startsWith('[System]') ||
    line.startsWith('[Inspector]') ||
    line.startsWith('[Publish]');
  const isDebug =
    line.startsWith('[Debug]') ||
    line.startsWith('[Time-Travel]') ||
    line.startsWith('Success');
  return isError
    ? 'text-rose-400'
    : isSystem
    ? 'text-amber-400'
    : isDebug
    ? 'text-cyan-300 font-semibold'
    : 'text-emerald-400';
};

export const TerminalLog: React.FC<{ logs: string[] }> = ({ logs }) => (
  <div className="flex-1 bg-[#080c16] border border-slate-800/90 rounded-lg p-2.5 font-mono text-[11px] space-y-1 overflow-y-auto">
    {logs.map((line, idx) => (
      <div key={idx} className={classifyLogLine(line)}>
        {line}
      </div>
    ))}
    <span className="inline-block w-1.5 h-3 bg-emerald-400 animate-pulse ml-0.5" />
  </div>
);
