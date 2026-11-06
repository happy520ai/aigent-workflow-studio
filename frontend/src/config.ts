// frontend/src/config.ts —— 前后端接线的唯一地址来源
// 开发（vite dev）：默认直连本机后端 8000；
// 生产构建（容器/nginx）：默认同源相对路径，由 nginx 反代到容器后端，
// 这样从任何 host 访问页面都能连对自己那一套后端。
const DEV = import.meta.env.DEV;

const devApiBase = 'http://localhost:8000/api/v1';
const prodApiBase = '/api/v1';

export const API_BASE =
  import.meta.env.VITE_API_BASE ?? (DEV ? devApiBase : prodApiBase);

const wsProtocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws';
const prodWsUrl =
  typeof window !== 'undefined'
    ? `${wsProtocol}://${window.location.host}/ws/telemetry`
    : 'ws://localhost:8000/ws/telemetry';

export const WS_URL =
  import.meta.env.VITE_WS_URL ?? (DEV ? 'ws://localhost:8000/ws/telemetry' : prodWsUrl);

// ---- T11/T43：管理令牌（sessionStorage，不落 localStorage、不入 URL 之外的地方） ----
export const ADMIN_TOKEN_KEY = 'aigent_admin_token';

export function getAdminToken(): string {
  try {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setAdminToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
    else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {
    // 隐私模式等场景下静默失败
  }
}

/** WS 连接地址：配置了管理令牌时追加 ?token=（服务端也接受 Sec-WebSocket-Protocol 子协议） */
export function buildWsUrl(): string {
  const token = getAdminToken();
  return token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;
}

/** REST 请求统一附带管理令牌头（T10/T43；未配置令牌时返回空对象） */
export function adminHeaders(): Record<string, string> {
  const token = getAdminToken();
  return token ? { 'X-Admin-Token': token } : {};
}
