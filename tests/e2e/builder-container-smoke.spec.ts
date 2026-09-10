import { test, expect, type Route } from '@playwright/test';

const EXTENDED_TIMEOUT = { timeout: 30_000 };
const CURRENT_USER = {
  id: '00000000-0000-4000-8000-000000000041',
  email: 'vnext-smoke@example.test',
  displayName: 'vNext Smoke',
  role: 'user',
  credits: 9,
  subscriptionStatus: 'free',
  isBanned: false,
  isGuest: false,
  createdAt: 1_700_000_000_000,
};

async function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  const requestOrigin = route.request().headers()['origin'] || 'http://localhost:3000';
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: {
      'Access-Control-Allow-Origin': requestOrigin,
      'Access-Control-Allow-Credentials': 'true',
      'Cache-Control': 'no-store',
    },
    body: JSON.stringify(body),
  });
}

async function installReadbackManifests(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/api/user/agent/toolchain/manifest', route => fulfillJson(route, {
    ok: true,
    name: 'Sovereign Universal Toolchain',
    version: 'smoke',
    runtime: 'embedded',
    policy: { draftPrOnly: true, confirmRequired: true },
  }));
  await page.route('**/api/user/agent/swarm/manifest', route => fulfillJson(route, {
    ok: true,
    runtime: 'openai-agents-sdk',
    manifest: {
      releaseMode: 'draft_pr_only',
      runtimeTruthRequired: true,
      agents: [
        { role: 'dispatcher', name: 'The Dispatcher', responsibility: 'Plan and route the mission.' },
        { role: 'judge', name: 'The Judge', responsibility: 'Reject unsupported publication claims.' },
      ],
    },
  }));
}

test.describe('Sovereign Control Surface vNext browser smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/me', route => fulfillJson(route, CURRENT_USER));
    await installReadbackManifests(page);
    await page.goto('/');
    await expect(page.locator('[data-testid="sovereign-chat-app"]')).toBeVisible(EXTENDED_TIMEOUT);
  });

  test('1. App loads the canonical vNext runtime-readback surface', async ({ page }) => {
    const app = page.locator('[data-testid="sovereign-chat-app"]');
    await expect(app).toHaveAttribute('data-layout', 'sovereign-control-surface-vnext');
    await expect(app).toHaveAttribute('data-primary-surface', 'sovereign-control-surface-vnext');
    await expect(app).toHaveAttribute('data-truth-scope', 'runtime-readback-only');
    await expect(app).toHaveAttribute('aria-label', 'Sovereign Control Surface');
    await expect(page.locator('[data-testid="sovereign-control-surface-vnext"]')).toBeVisible();
    await expect(page.locator('[data-testid="vnext-command-surface"]')).toBeVisible();
    await expect(page.locator('[data-testid="vnext-runtime-monitor"]')).toBeVisible();
    await expect(page.locator('[data-testid="vnext-workspace-projection"]')).toBeVisible();
    await expect(page.locator('[data-testid="vnext-publication-inspector"]')).toBeVisible();
  });

  test('2. Operator UI projects the real authenticated backend session instead of a frontend token', async ({ page }) => {
    await page.getByTestId('operator-auth-btn').click();
    const dialog = page.getByRole('dialog', { name: 'Sovereign account session' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('BACKEND SESSION READBACK')).toBeVisible();
    await expect(dialog.getByText('vNext Smoke')).toBeVisible();
    await expect(dialog.getByText('AUTHENTICATED')).toBeVisible();
    await expect(dialog.locator('input[placeholder="svk_…"]')).toHaveCount(0);
  });

  test('3. Toolchain and swarm panels are server-readback projections, not local switches', async ({ page }) => {
    await page.getByRole('button').filter({ hasText: 'TOOLCHAIN' }).click();
    const toolchainDialog = page.getByRole('dialog', { name: 'TOOLCHAIN CONFIGURATION // EXECUTION DRIVERS' });
    await expect(toolchainDialog).toBeVisible();
    await expect(toolchainDialog.getByText('Sovereign Universal Toolchain', { exact: true })).toBeVisible();
    await expect(toolchainDialog.getByText(/Read-only server-owned execution manifest/)).toBeVisible();
    await toolchainDialog.getByRole('button', { name: 'Close' }).click();

    await page.getByRole('button').filter({ hasText: 'SWARM' }).click();
    const swarmDialog = page.getByRole('dialog', { name: 'SWARM REGISTRY // BIOMODULAR NODES' });
    await expect(swarmDialog).toBeVisible();
    await expect(swarmDialog.getByText('The Dispatcher', { exact: true })).toBeVisible();
    await expect(swarmDialog.getByText('The Judge', { exact: true })).toBeVisible();
    await expect(swarmDialog.getByText(/does not locally enable or disable execution capabilities/)).toBeVisible();
  });

  test('4. Architecture panel documents the exact production adapter truth boundary', async ({ page }) => {
    await page.getByTestId('open-architecture-btn').click();
    const dialog = page.getByRole('dialog', { name: 'PRODUCTION ADAPTER // TRUTH BOUNDARY' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('NO AUTOMATIC SIMULATOR FALLBACK', { exact: true })).toBeVisible();
    await expect(dialog.getByText('/api/user/agent/swarm/run', { exact: true })).toBeVisible();
    await expect(dialog.getByText('/api/user/agent/jobs/:jobId/draft-pr/create', { exact: true })).toBeVisible();
    await expect(dialog.getByText(/GitHub readback/).first()).toBeVisible();
  });

  test('5. vNext fixed projections remain reachable at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator('[data-testid="mobile-bottom-nav"]')).toBeVisible();
    await expect(page.getByRole('button', { name: /COMMAND/ })).toBeVisible();
    await page.getByRole('button', { name: /EVIDENCE/ }).click();
    await expect(page.locator('[data-testid="vnext-runtime-monitor"]')).toBeVisible();
    await page.getByRole('button', { name: /WORKSPACE/ }).click();
    await expect(page.locator('[data-testid="vnext-workspace-projection"]')).toBeVisible();
    await page.getByRole('button', { name: /PUBLISH/ }).click();
    await expect(page.locator('[data-testid="vnext-publication-inspector"]')).toBeVisible();
    await expect(page.getByTestId('vnext-create-draft-pr')).toHaveCount(0);
  });

  test('6. Missing session fails closed before any protected agent request', async ({ page }) => {
    await page.unroute('**/api/auth/me');
    await page.unroute('**/api/user/agent/toolchain/manifest');
    await page.unroute('**/api/user/agent/swarm/manifest');
    await page.route('**/api/auth/me', route => fulfillJson(route, { error: 'unauthorized' }, 401));
    await page.route('**/api/auth/guest', route => fulfillJson(route, { error: 'guest unavailable' }, 503));
    await page.evaluate(() => window.localStorage.clear());

    const protectedRequests: string[] = [];
    page.on('request', request => {
      const pathname = new URL(request.url()).pathname;
      if (pathname.startsWith('/api/user/agent/')) protectedRequests.push(`${request.method()} ${pathname}`);
    });

    await page.reload();
    const composer = page.getByLabel('Mission an Sovereign');
    await expect(composer).toBeVisible(EXTENDED_TIMEOUT);
    await composer.fill('Prüfe das Repository.');
    await page.getByTestId('builder__start-task').click();

    await expect(page.getByText(/Backend session readback is still pending|Repository execution requires an authenticated account/)).toBeVisible();
    await expect(page.getByRole('dialog', { name: 'Sovereign account session' })).toBeVisible();
    expect(protectedRequests).toEqual([]);
  });

  test('7. The evidence observatory route remains independently reachable', async ({ page }) => {
    await page.goto('/observatory');
    await expect(page.locator('[data-testid="evidence-observatory-atlas"]')).toBeVisible(EXTENDED_TIMEOUT);
    await expect(page.locator('[data-testid="sovereign-chat-app"]')).toHaveCount(0);
  });
});
