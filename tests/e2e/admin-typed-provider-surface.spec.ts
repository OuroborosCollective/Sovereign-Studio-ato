import { expect, test, type Page, type Route } from '@playwright/test';

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET, POST, PATCH, OPTIONS',
  'access-control-allow-headers': 'authorization, content-type, accept',
};

type Call = { method: string; path: string };

function json(route: Route, payload: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: 'application/json',
    headers: CORS,
    body: JSON.stringify(payload),
  });
}

async function installAdminAssetRewrite(page: Page): Promise<void> {
  // The production backend serves the relative Vite asset namespace at
  // /admin/assets/*. Vite preview only exposes /assets/*, so emulate that
  // narrow delivery boundary without changing the production artifact base.
  await page.route('**/admin/assets/**', async route => {
    const url = new URL(route.request().url());
    url.pathname = url.pathname.replace(/^\/admin\/assets\//, '/assets/');
    await route.continue({ url: url.toString() });
  });
}

function provider(
  id: string,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id,
    sourceType: 'freellmapi-direct',
    providerSurfaceKind: 'free-revolver',
    lifecycle: 'active',
    canonicalAction: 'revolver-discover',
    label: 'FreeLLM API',
    apiBase: 'http://freellmapi:3001/v1',
    modelsUrl: 'http://freellmapi:3001/v1/models',
    authMode: 'managed-bearer',
    keyHint: 'owner-managed',
    status: 'healthy',
    lastHttpStatus: 200,
    lastErrorCode: null,
    lastDiscoveredAt: null,
    lastCheckedAt: null,
    enabled: true,
    ownerRequestId: null,
    models: [],
    ...overrides,
  };
}

async function installAdminMock(page: Page, calls: Call[]): Promise<void> {
  let omniRouteReady = false;
  await page.route('**/api/admin/**', async route => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;

    if (method === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    calls.push({ method, path });

    if (method === 'GET' && path === '/api/admin/ping') {
      await json(route, {
        ok: true,
        authMode: 'bearer',
        id: 'e2e-admin',
        email: 'e2e-admin@example.invalid',
        displayName: 'E2E Admin',
        role: 'admin',
        credits: 0,
        subscriptionStatus: 'active',
        isBanned: false,
        createdAt: '2026-08-23T00:00:00.000Z',
        lastActiveAt: null,
      });
      return;
    }

    if (method === 'GET' && path === '/api/admin/llm/routes') {
      await json(route, {
        routes: [],
        billingCategories: [],
        revolverStats: null,
        revolverV3: null,
        manualCreditsPerUnitEditing: false,
        legacyDirectRouteCount: 0,
        legacyDirectRoutePolicy: 'fail-closed',
      });
      return;
    }

    if (method === 'GET' && path === '/api/admin/llm/revolver-v3/providers') {
      await json(route, {
        ok: true,
        truthOwner: 'postgresql-owner-input-direct-freellm',
        keyStorage: 'owner-managed-direct-freellm',
        activationRule: 'managed-free-quota-plus-revision-bound-double-canary-without-positive-cost-contradiction',
        minimumReadyRoutes: 5,
        providers: [
          provider('freellmapi-source'),
          provider('0609e75c-8c48-59db-80a4-3155b823205b', {
            sourceType: 'external-free-provider',
            providerSurfaceKind: 'omniroute-auto',
            canonicalAction: 'omniroute-refresh',
            label: 'OmniRoute Auto',
            apiBase: 'http://omniroute:20128/v1',
            modelsUrl: null,
            authMode: 'none',
            keyHint: 'ohne Key',
            status: 'degraded',
            lastHttpStatus: 401,
            lastErrorCode: 'omniroute_canary_http_401',
          }),
          provider('freellmpool-source', {
            sourceType: 'freellmpool-private',
            providerSurfaceKind: 'retired-reference',
            lifecycle: 'historical',
            canonicalAction: 'none',
            label: 'FreeLLMPool 0.11.4 · privater Docker',
            apiBase: 'http://freellmpool:8080/v1',
            modelsUrl: null,
            status: 'disabled',
            enabled: false,
            lastHttpStatus: null,
            lastErrorCode: 'freellmpool_replaced_by_omniroute',
          }),
        ],
      });
      return;
    }

    if (method === 'GET' && path === '/api/admin/llm/omniroute/status') {
      if (omniRouteReady) {
        await json(route, {
          ok: true,
          routeSource: 'omniroute',
          routeId: 'sovereign-omniroute-auto',
          modelId: 'sovereign-omniroute:auto',
          apiBase: 'http://omniroute:20128/v1',
          disabled: false,
          activationState: 'ready',
          blocker: null,
          confirmationCount: 2,
          catalogModelCount: 42,
          receiptSha256: 'c'.repeat(64),
          sourceRevision: 'a'.repeat(40),
          imageDigest: 'sha256:' + 'b'.repeat(64),
          freeLlmApiChanged: false,
          rawProviderResponsesReturned: false,
        });
        return;
      }
      await json(route, {
        ok: false,
        routeSource: 'omniroute',
        routeId: 'sovereign-omniroute-auto',
        modelId: 'sovereign-omniroute:auto',
        apiBase: 'http://omniroute:20128/v1',
        disabled: true,
        activationState: 'blocked',
        blocker: 'omniroute_canary_http_401',
        confirmationCount: 0,
        receiptSha256: null,
        sourceRevision: 'a'.repeat(40),
        imageDigest: `sha256:${'b'.repeat(64)}`,
        freeLlmApiChanged: false,
        rawProviderResponsesReturned: false,
      });
      return;
    }

    if (method === 'POST' && path === '/api/admin/llm/omniroute/refresh') {
      omniRouteReady = true;
      await json(route, {
        ok: true,
        routeSource: 'omniroute',
        routeId: 'sovereign-omniroute-auto',
        modelId: 'sovereign-omniroute:auto',
        apiBase: 'http://omniroute:20128/v1',
        disabled: false,
        activationState: 'ready',
        blocker: null,
        confirmationCount: 2,
        catalogModelCount: 42,
        receiptSha256: 'c'.repeat(64),
        sourceRevision: 'a'.repeat(40),
        imageDigest: `sha256:${'b'.repeat(64)}`,
        freeLlmApiChanged: false,
        rawProviderResponsesReturned: false,
      });
      return;
    }

    if (method === 'GET' && path === '/api/admin/llm/openrouter/status') {
      await json(route, {
        status: 'ready',
        deploymentStatus: 'ready',
        routeId: 'openrouter-root',
        transport: 'openrouter',
        keyStored: true,
        keyHint: '…paid',
        selectableModels: 291,
        lastCanaryRequestId: null,
        lastCanaryAt: null,
        lastErrorCode: null,
        secretValuesReturned: false,
      });
      return;
    }

    if (method === 'GET' && path === '/api/admin/llm/openrouter/free/status') {
      await json(route, {
        ok: true,
        status: 'OPENROUTER_FREE_RUNTIME_STATUS',
        freeExecutionKey: {},
        managementKey: {},
        route: {},
        managementTableAvailable: true,
        managementTableBlocker: null,
        routingPolicy: {
          priority: 5,
          providerModel: 'openrouter/free',
          fallbackAfterQuota: 'freellm',
          paidFallbackAllowed: false,
          accountWideQuotaScope: 'openrouter:account:free-models',
        },
        runtimeIdentity: {},
        secretValuesReturned: false,
      });
      return;
    }

    await json(route, { error: `unexpected ${method} ${path}` }, 404);
  });
}

test('renders every typed provider surface and invokes only the canonical OmniRoute action', async ({ page }) => {
  const calls: Call[] = [];
  await installAdminAssetRewrite(page);
  await installAdminMock(page, calls);

  await page.goto('/admin/');
  await expect(page.getByPlaceholder('Admin-Key eingeben')).toBeVisible();
  await page.getByPlaceholder('Admin-Key eingeben').fill('e2e-admin-key');
  await page.getByRole('button', { name: 'Verbinden & speichern' }).click();

  await page.getByRole('button', { name: 'LLM', exact: true }).click();
  await expect(page.getByTestId('provider-surface-openrouter-paid')).toBeVisible();

  await page.getByTestId('provider-surface-tab-free').click();
  await expect(page.getByTestId('provider-surface-openrouter-free')).toBeVisible();
  await expect(page.getByTestId('provider-surface-omniroute')).toBeVisible();
  await expect(page.getByTestId('provider-surface-freellm-api')).toBeVisible();
  await expect(page.getByTestId('provider-surface-retired-freellmpool')).toBeVisible();
  await expect(page.getByTestId('free-revolver-minimum-ready')).toContainText('0/5');

  await Promise.all([
    page.waitForRequest(request => (
      request.method() === 'POST'
      && new URL(request.url()).pathname === '/api/admin/llm/omniroute/refresh'
    )),
    page.getByTestId('provider-action-omniroute-refresh').click(),
  ]);

  const omniSurface = page.getByTestId('provider-surface-omniroute');
  await expect(omniSurface).toContainText('ready');
  await expect(omniSurface).toContainText('2/2');

  const refreshCallIndex = calls.findIndex(call => (
    call.method === 'POST'
    && call.path === '/api/admin/llm/omniroute/refresh'
  ));
  expect(refreshCallIndex).toBeGreaterThanOrEqual(0);
  expect(calls.slice(refreshCallIndex + 1).some(call => (
    call.method === 'GET'
    && call.path === '/api/admin/llm/omniroute/status'
  ))).toBe(true);
  expect(calls.some(call => (
    call.method === 'POST'
    && call.path.endsWith('/revolver-v3/providers/0609e75c-8c48-59db-80a4-3155b823205b/discover')
  ))).toBe(false);
});
