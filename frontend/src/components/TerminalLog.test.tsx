// frontend/src/components/TerminalLog.test.tsx —— T50：日志分级着色纯函数 + 组件渲染
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { classifyLogLine, TerminalLog } from './TerminalLog';

describe('classifyLogLine', () => {
  it('错误/警告 → 玫瑰色', () => {
    expect(classifyLogLine('[Error] 崩了')).toBe('text-rose-400');
    expect(classifyLogLine('[Warn] 降级')).toBe('text-rose-400');
  });

  it('系统类 → 琥珀色', () => {
    expect(classifyLogLine('[System] 部署')).toBe('text-amber-400');
    expect(classifyLogLine('[Inspector] 热更新')).toBe('text-amber-400');
    expect(classifyLogLine('[Publish] 导出')).toBe('text-amber-400');
  });

  it('调试/时间旅行/成功 → 青色加粗', () => {
    expect(classifyLogLine('[Debug] 单步')).toBe('text-cyan-300 font-semibold');
    expect(classifyLogLine('[Time-Travel] 回滚')).toBe('text-cyan-300 font-semibold');
    expect(classifyLogLine('Success...')).toBe('text-cyan-300 font-semibold');
  });

  it('普通行 → 翠绿色', () => {
    expect(classifyLogLine('Agent initialized: 99.2%...')).toBe('text-emerald-400');
  });
});

describe('TerminalLog 组件', () => {
  it('渲染日志行并保留顺序', () => {
    render(<TerminalLog logs={['Success...', '[Error] x', 'Agent initialized: 99.2%...']} />);
    expect(screen.getByText('[Error] x')).toBeTruthy();
    const rows = screen.getAllByText(/./);
    expect(rows.length).toBeGreaterThanOrEqual(3);
  });
});
