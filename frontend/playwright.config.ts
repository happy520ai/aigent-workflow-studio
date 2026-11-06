import { defineConfig, devices } from '@playwright/test';

// T51：E2E —— 后端（临时库 + 令牌）与前端（vite dev 指向 E2E 后端）双 webServer。
export default defineConfig({
  globalSetup: './e2e/global-setup.ts',
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5183',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  outputDir: 'test-results',
  webServer: [
    {
      command: '..\\backend\\.venv\\Scripts\\python.exe -m uvicorn perfect_main:app --app-dir ..\\backend --host 127.0.0.1 --port 8021',
      port: 8021,
      reuseExistingServer: !process.env.CI,
      env: {
        AIGENT_ADMIN_TOKEN: 'e2e-token',
        AIGENT_DB_PATH: '..\\backend\\_e2e_ckpt.db',
        AIGENT_PERSIST_TOPOLOGY: '1',
        // E2E 前端跑在 5183：必须加入 CORS/WS Origin 白名单（T11），否则 WS 握手 4403
        CORS_ORIGINS: 'http://127.0.0.1:5183,http://localhost:5183',
      },
    },
    {
      command: 'npm run dev -- --port 5183 --strictPort',
      port: 5183,
      reuseExistingServer: !process.env.CI,
      env: {
        VITE_API_BASE: 'http://127.0.0.1:8021/api/v1',
        VITE_WS_URL: 'ws://127.0.0.1:8021/ws/telemetry',
      },
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
