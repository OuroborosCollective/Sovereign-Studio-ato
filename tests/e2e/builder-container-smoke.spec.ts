import { test, expect, type Route } from '@playwright/test';

const EXTENDED_TIMEOUT = { timeout: 30_000 };
const CURRENT_USER = {
  id: '00000000-0000-4000-8000-000000000041',
  email: 'play-release-smoke@example.test',
  displayName: 'Play Release Smoke',
  role: 'user',
  credits: 9,
  subscriptionStatus: 'free',
  isBanned: false,
  createdAt: 1_700_000_000_000,
};
const FREE_ROUTE = {
  id: '00000000-0000-4000-8000-000000000777',
  defaultModelId: 'free/test-model',
  label: 'Verified Free Test Route',
  description: 'Play Release browser smoke',
  provider: 'freellm',
  billingCategory: 'free',
  priority: 1,
  enabled: true,
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

test.describe('Current-session Play Release browser smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/me', route => fulfillJson(route, CURRENT_USER));
    await page.route('**/api/llm/routes**', route => fulfillJson(route, { routes: [FREE_ROUTE] }));
    await page.route('**/health/ready', route => fulfillJson(route, { ok: true, configured: true }));
    await page.goto('/');
    await expect(page.locator('[data-testid="sovereign-chat-app"]')).toBeVisible(EXTENDED_TIMEOUT);
  });

  test('1. App loads the canonical current-session Play Release surface', async ({ page }) => {
    const app = page.locator('[data-testid="sovereign-chat-app"]');
    await expect(app).toHaveAttribute('data-layout', 'chat-first-agent-zero-background');
    await expect(app).toHaveAttribute('data-primary-surface', 'play-release-chat');
    await expect(app).toHaveAttribute('data-truth-scope', 'current-chat-session-only');
    await expect(app).toHaveAttribute('aria-label', 'Sovereign Chat');

    const release = page.locator('[data-testid="sovereign-release-chat"]');
    await expect(release).toBeVisible();
    await expect(release).toHaveAttribute('data-layout', 'play-release-chat');
    await expect(page.locator('[data-testid="play-release-menu-frame"]')).toBeVisible();
    await expect(page.getByLabel('Nachricht an Sovereign')).toBeVisible();
    await expect(page.getByLabel('LLM Route')).toBeVisible();
    await expect(page.locator('[data-testid="live-workspace-monitor-desktop"]')).toHaveCount(0);
    await expect(page.locator('[data-layout="chat-primary-agent-zero-background"]')).toHaveCount(0);
  });

  test('2. GitHub access remains protected and separate from repository action consent', async ({ page }) => {
    await page.getByRole('button', { name: 'GitHub', exact: true }).click();

    const preview = page.locator('[data-testid="github-action-preview"]');
    await expect(preview).toBeVisible();
    await expect(page.getByRole('button', { name: 'GitHub sicher verbinden', exact: true })).toBeVisible();

    const accessCard = page.getByRole('group', { name: 'GitHub-Zugang' });
    await expect(accessCard).toBeVisible();
    await accessCard.getByRole('button', { name: 'Zugang eingeben' }).click();

    const accessDialog = page.getByRole('dialog', { name: 'GitHub-Zugang' });
    await expect(accessDialog).toBeVisible();
    await expect(accessDialog.getByLabel(/GitHub Token/)).toHaveAttribute('type', 'password');
    await expect(page.getByRole('button', { name: 'Repository-Ausführung starten' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Draft PR erstellen' })).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(accessDialog).toHaveCount(0);
  });

  test('3. Composer and server-authoritative route picker stay compact and explicit', async ({ page }) => {
    const composer = page.getByLabel('Nachricht an Sovereign');
    await expect(composer).toBeVisible();

    await composer.fill('');
    await expect(page.getByRole('button', { name: 'Senden', exact: true })).toBeDisabled();
    await composer.fill('Prüfe den Build und bereite nur einen Draft PR vor.');
    await expect(page.getByRole('button', { name: 'Senden', exact: true })).toBeEnabled();

    const routePicker = page.getByLabel('LLM Route');
    await expect(routePicker).toBeVisible();
    await expect(routePicker).toHaveValue('');
    await expect(routePicker.locator('option')).toHaveCount(2);
    await expect(routePicker.locator(`option[value="${FREE_ROUTE.id}"]`)).toHaveText('FREE · Verified Free Test Route');

    await page.getByRole('button', { name: 'Modelle', exact: true }).click();
    await routePicker.selectOption(FREE_ROUTE.id);
    await expect(routePicker).toHaveValue(FREE_ROUTE.id);
    await expect(page.getByText('Aktiv: FREE · Verified Free Test Route')).toBeVisible();
  });

  test('4. Current-session navigation stays primary without resurrecting Builder history', async ({ page }) => {
    for (const label of ['Chat', 'GitHub', 'Modelle', 'Konto']) {
      await expect(page.getByRole('button', { name: label, exact: true })).toBeVisible();
    }
    await expect(page.locator('[data-testid="sovereign-release-chat"]')).toBeVisible();
    await expect(page.locator('[data-testid="monitor-runtime-action-trace"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="sovereign-chat-primary"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="monitor-communication-dock"]')).toHaveCount(0);
  });

  test('5. Play Release controls remain reachable at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator('[data-testid="sovereign-chat-app"]')).toBeVisible();
    await expect(page.locator('[data-testid="sovereign-release-chat"]')).toBeVisible();
    await expect(page.locator('[data-testid="play-release-menu-frame"]')).toBeVisible();
    await expect(page.getByLabel('Nachricht an Sovereign')).toBeVisible();

    await page.getByRole('button', { name: 'GitHub', exact: true }).click();
    await expect(page.locator('[data-testid="github-action-preview"]')).toBeVisible();
    await expect(page.getByRole('group', { name: 'GitHub-Zugang' })).toBeVisible();
  });

  test('6. Missing session fails closed before LLM or repository execution', async ({ page }) => {
    await page.unroute('**/api/auth/me');
    await page.route('**/api/auth/me', route => fulfillJson(route, { error: 'unauthorized' }, 401));
    await page.route('**/api/auth/guest', route => fulfillJson(route, { error: 'guest unavailable' }, 503));
    await page.evaluate(() => window.localStorage.clear());

    const protectedRequests: string[] = [];
    page.on('request', request => {
      const pathname = new URL(request.url()).pathname;
      if (pathname === '/api/llm/chat' || pathname.startsWith('/api/user/agent/')) {
        protectedRequests.push(`${request.method()} ${pathname}`);
      }
    });

    await page.reload();
    const composer = page.getByLabel('Nachricht an Sovereign');
    await expect(composer).toBeVisible(EXTENDED_TIMEOUT);
    await composer.fill('https://github.com/example/public-repo');
    await page.getByRole('button', { name: 'Senden', exact: true }).click();

    await expect(page.getByText('Die pseudonyme Gast-Sitzung wird noch vorbereitet. Bitte den Auftrag gleich erneut senden.')).toBeVisible();
    await expect(page.getByRole('dialog', { name: 'Anmelden', exact: true })).toHaveCount(0);
    expect(protectedRequests).toEqual([]);
  });

  test('7. The evidence observatory route remains independently reachable', async ({ page }) => {
    await page.goto('/observatory');
    await expect(page.locator('[data-testid="evidence-observatory-atlas"]')).toBeVisible(EXTENDED_TIMEOUT);
    await expect(page.locator('[data-testid="sovereign-chat-app"]')).toHaveCount(0);
  });
});
