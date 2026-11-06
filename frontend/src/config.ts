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
