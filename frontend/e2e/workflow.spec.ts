// frontend/e2e/workflow.spec.ts —— T51：端到端主链路
// 覆盖：加载并连接后端 → 加节点 → 连线 → 成环被拒 → node_update 流量 → 导出 ZIP →
//       时间旅行回滚 → 401 登录流（错误令牌被拒 / 正确令牌放行）。
import { expect, test, type Page } from '@playwright/test';

const SHOT_DIR = '../docs/e2e-screenshots';

// E2E 后端配置了管理令牌：页面加载前注入 sessionStorage（覆盖 T10/T11 令牌链路）
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('aigent_admin_token', 'e2e-token'));
});

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `${SHOT_DIR}/${name}.png`, fullPage: false });
}

// 后端以持久化拓扑运行（复用服务时残留旧节点）：主链路前先重置到默认拓扑
async function resetTopology(page: Page): Promise<void> {
  await page.request.post('http://127.0.0.1:8021/api/v1/workflow/control', {
    data: { action: 'reset' },
    headers: { 'X-Admin-Token': 'e2e-token' },
  });
}

/** 点击后断言出现；未出现则重试点击（重连风暴期 UI 点击偶发丢失） */
async function clickUntilVisible(page: Page, locator: import('@playwright/test').Locator, assertLocator: import('@playwright/test').Locator, tries = 3): Promise<void> {
  for (let i = 0; i < tries; i++) {
    await locator.click();
    try {
      await assertLocator.waitFor({ state: 'visible', timeout: 3_000 });
      return;
    } catch {
      // 再试一次
    }
  }
  await assertLocator.waitFor({ state: 'visible', timeout: 5_000 }); // 最后一次给明确报错
}

async function waitBackendConnected(page: Page): Promise<void> {
  await expect(page.getByText('已连接后端')).toBeVisible({ timeout: 35_000 });
}

/** 打开拓扑抽屉读「连线 (N)」计数后关闭 */
async function topologyEdgeCount(page: Page): Promise<number> {
  await clickUntilVisible(
    page,
    page.getByRole('button', { name: '拓扑与运行记录' }),
    page.getByText(/连线 \(\d+\)/)
  );
  const label = await page.getByText(/连线 \(\d+\)/).innerText();
  await page.getByRole('button', { name: '清空侧栏' }).click();
  const m = label.match(/连线 \((\d+)\)/);
  return m ? Number(m[1]) : -1;
}

async function terminalText(page: Page): Promise<string> {
  return (await page.locator('body').innerText()) ?? '';
}

test('主链路：加载/加节点/连线/成环被拒/运行流量', async ({ page }) => {
  // node_update 帧监听必须先于 goto：WS 可能在断言连接前就已建立
  const nodeUpdateReceived = new Promise<string>((resolve) => {
    page.on('websocket', (ws) => {
      ws.on('framereceived', (frame) => {
        if (frame.payload.toString().includes('"node_update"')) resolve(frame.payload.toString());
      });
    });
  });
  await resetTopology(page);
  await page.goto('/');
  await expect(page.getByText('前端智能体工作流平台')).toBeVisible();
  await waitBackendConnected(page);
  await shot(page, '01-loaded-connected');

  // —— 加节点（真实后端）：点击「自然语言理解 (NLU)」——
  await page.getByRole('button', { name: /自然语言理解 \(NLU\)/ }).click();
  await expect(page.locator('div.cursor-grab').filter({ hasText: '自然语言理解' })).toHaveCount(1, { timeout: 15_000 });
  await shot(page, '02-node-added');

  // —— 连线：Shift+点击 源 → Shift+点击 目标（断言：POST 200 + 拓扑抽屉连线数 +1）——
  const edgeCountBefore = await topologyEdgeCount(page);

  const edgePost = page.waitForResponse(
    (r) => r.url().includes('/workflow/edges') && r.request().method() === 'POST',
    { timeout: 20_000 }
  );
  const eventNode = page.locator('div.cursor-grab').filter({ hasText: '事件捕获' }).first();
  const nluNode = page.locator('div.cursor-grab').filter({ hasText: '自然语言理解' }).first();
  await eventNode.click({ modifiers: ['Shift'] });
  await nluNode.click({ modifiers: ['Shift'] });
  const edgeResp = await edgePost;
  expect(edgeResp.status()).toBe(200);
  expect(await topologyEdgeCount(page)).toBe(edgeCountBefore + 1);

  // —— 成环被拒：DOM渲染引擎 → 意图识别智能体（intent→dom 已存在）——
  const edgeCountAfterAdd = await topologyEdgeCount(page);
  const cyclePost = page.waitForResponse(
    (r) => r.url().includes('/workflow/edges') && r.request().method() === 'POST',
    { timeout: 20_000 }
  );
  const domNode = page.locator('div.cursor-grab').filter({ hasText: '页面渲染引擎' }).first();
  const intentNode = page.locator('div.cursor-grab').filter({ hasText: '意图识别智能体' }).first();
  await domNode.click({ modifiers: ['Shift'] });
  await intentNode.click({ modifiers: ['Shift'] });
  const cycleResp = await cyclePost;
  expect(cycleResp.status()).toBe(409);
  expect((await cycleResp.json()).detail).toContain('环路');
  expect(await topologyEdgeCount(page)).toBe(edgeCountAfterAdd); // 拓扑未被改动
  await shot(page, '03-cycle-rejected');

  // —— 运行流量：等待 page 级监听捕获 node_update 帧 ——
  await page.getByRole('button', { name: '运行 Run' }).click();
  const frame = await Promise.race([
    nodeUpdateReceived,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), 25_000)),
  ]);
  expect(frame, '应在 25s 内收到 node_update 帧').toBeTruthy();
  expect(frame!).toContain('sandbox_html');
  await shot(page, '04-node-update-received');
});

test('导出 ZIP 下载', async ({ page }) => {
  await page.goto('/');
  await waitBackendConnected(page);
  // 导出走「同步预开窗口 → 异步赋签名地址」：下载发生在新开的 popup 页
  const downloadPromise = page.context().waitForEvent('download', { timeout: 30_000 });
  const popupPromise = page.context().waitForEvent('page');
  await page.getByRole('button', { name: '导出工程 ZIP' }).click();
  await popupPromise.catch(() => null); // popup 可能随下载开始而关闭，属正常
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.zip$/);
  await download.saveAs(`../docs/e2e-screenshots/export-bundle.zip`);
});

test('时间旅行回滚', async ({ page }) => {
  test.setTimeout(150_000); // 连接等待 + 断点累计 + 模态流程
  await page.goto('/');
  await waitBackendConnected(page);
  // 等 DAG 轮次产生断点
  await page.waitForTimeout(3_000);
  await clickUntilVisible(
    page,
    page.getByRole('button', { name: '打开沙盒与断点' }),
    page.getByText('神经元沙盒与时间旅行控制台')
  );
  await page.getByRole('button', { name: /时间旅行断点 \(\d+\)/ }).click();
  const rollbackBtn = page.getByRole('button', { name: '回滚此断点' }).first();
  await expect(rollbackBtn).toBeVisible({ timeout: 15_000 });
  // 断言以 restore 响应为准（服务端确定性证据）；客户端日志行会被引擎日志快速冲掉
  const restoreResp = page.waitForResponse(
    (r) => r.url().includes('/checkpoints/') && r.url().includes('/restore'),
    { timeout: 20_000 }
  );
  await rollbackBtn.click();
  const resp = await restoreResp;
  expect(resp.status()).toBe(200);
  await shot(page, '05-time-travel-restored');
  // 关闭模态后，服务端 "[Time-Travel] 已回滚至历史断点" 日志在 12 行窗口内仍应可见
  await page.keyboard.press('Escape');
  await expect(page.getByText(/\[Time-Travel\] 已回滚至历史断点/).first()).toBeVisible({ timeout: 12_000 });
});

test('401 登录流：错误令牌被拒 → 正确令牌放行', async ({ page }) => {
  // 本用例反向验证：错误令牌下 WS 4401、REST 401（不等待连接），设置抽屉可自救
  await page.addInitScript(() => sessionStorage.setItem('aigent_admin_token', 'wrong-token'));
  await page.goto('/');
  await expect(page.getByText('前端智能体工作流平台')).toBeVisible();
  await clickUntilVisible(
    page,
    page.getByRole('button', { name: '大模型设置' }),
    page.getByText('大模型设置 (LLM Settings)')
  );

  // 错误令牌：读取设置被 401 拒绝 → toast 指引
  const tokenInput = page.getByPlaceholder('AIGENT_ADMIN_TOKEN');
  await tokenInput.fill('wrong-token');
  await page.waitForTimeout(1_500); // 触发 GET /settings/llm（抽屉打开即拉取）
  await expect(page.getByText(/需要管理令牌/).first()).toBeVisible({ timeout: 15_000 });
  await shot(page, '06-401-toast');

  // 正确令牌：读取成功并保存
  await tokenInput.fill('e2e-token');
  await page.getByText(/当前密钥|读取中/).first().waitFor({ timeout: 15_000 });
  await page.getByRole('button', { name: '保存模型配置' }).click();
  await expect(page.getByText(/已更新|当前密钥/).first()).toBeVisible({ timeout: 15_000 });
  await shot(page, '07-token-accepted');
});
