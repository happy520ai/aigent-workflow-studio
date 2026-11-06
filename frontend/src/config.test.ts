// frontend/src/config.test.ts —— T50：config.ts 地址逻辑与令牌头单测
import { beforeEach, describe, expect, it } from 'vitest';
import { adminHeaders, buildWsUrl, getAdminToken, setAdminToken, WS_URL } from './config';

describe('config.ts', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('默认 WS 地址指向本机后端 8000（开发态）', () => {
    expect(WS_URL).toContain('ws://localhost:8000/ws/telemetry');
  });

  it('令牌存取走 sessionStorage（不落 localStorage / 不入 URL 外部）', () => {
    expect(getAdminToken()).toBe('');
    setAdminToken('tok-123');
    expect(getAdminToken()).toBe('tok-123');
    expect(sessionStorage.getItem('aigent_admin_token')).toBe('tok-123');
    // config.setAdminToken 只使用 sessionStorage（实现层面唯一存储点）；此处断言移除条目即清空
    setAdminToken('');
    expect(getAdminToken()).toBe('');
    expect(sessionStorage.getItem('aigent_admin_token')).toBeNull();
  });

  it('buildWsUrl：有令牌追加 ?token=（URI 编码），无令牌保持原样', () => {
    setAdminToken('abc123');
    expect(buildWsUrl()).toBe(`${WS_URL}?token=abc123`);
    setAdminToken('需要编码/空格');
    expect(buildWsUrl()).toBe(`${WS_URL}?token=${encodeURIComponent('需要编码/空格')}`);
    setAdminToken('');
    expect(buildWsUrl()).toBe(WS_URL);
  });

  it('adminHeaders：有令牌带 X-Admin-Token，无令牌空对象', () => {
    expect(adminHeaders()).toEqual({});
    setAdminToken('tok-x');
    expect(adminHeaders()).toEqual({ 'X-Admin-Token': 'tok-x' });
  });
});
