import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { expect, test, type Route } from '@playwright/test';

const REPOSITORY_ROOT = process.cwd();
const REPORT_RELATIVE_PATH = '.security-reports/sovereign-frontend-endpoints.json';
const REPORT_PATH = path.join(REPOSITORY_ROOT, REPORT_RELATIVE_PATH);
const DEFAULT_APP_ORIGIN = 'http://localhost:3000';

interface EndpointContractReport {
  schemaVersion: string;
  status: 'pass' | 'fail';
  revision: string;
  reportSha256: string;
  summary: {
    frontendModuleCount: number;
    importEdgeCount: number;
    legacyImportViolationCount: number;
    frontendCallCount: number;
    activeRequestCount: number;
    boundActiveRequestCount: number;
    unmatchedActiveRequestCount: number;
    methodMismatchCount: number;
    methodUnknownCount: number;
    activeMutationRequestCount: number;
    activeMutationWithoutTestEvidenceCount: number;
    activeReadRequestCount: number;
    activeReadWithoutTestEvidenceCount: number;
    backendRouteCount: number;
    externalRequestCount: number;
    activeExternalRequestCount: number;
    externalMethodUnknownCount: number;
  };
  bindings: Array<{
    call: {
      path: string;
      method: string;
      file: string;
      source_kind: string;
      active_surface: boolean;
    };
    status: string;
    backendRoutes: Array<{ path: string; methods: string[]; file: string }>;
    testReferences: {
      unit: string[];
      backend: string[];
      e2e: string[];
    };
  }>;
  errors: unknown[];
  truthBoundary: {
    repositoryContractEvidence: boolean;
    networkRequestsPerformed: boolean;
    runtimeReachabilityProven: boolean;
    authenticationProven: boolean;
    targetEffectProven: boolean;
    externalTargetReachabilityProven: boolean;
  };
}

function compileEndpointContractReport(): EndpointContractReport {
  fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
  execFileSync(
    'python3',
    [
      'scripts/frontend_endpoint_contracts.py',
      '--repo',
      '.',
      '--report',
      REPORT_RELATIVE_PATH,
      '--check',
    ],
    {
      cwd: REPOSITORY_ROOT,
      encoding: 'utf8',
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );
  return JSON.parse(fs.readFileSync(REPORT_PATH, 'utf8')) as EndpointContractReport;
}

async function fulfillJson(route: Route, body: unknown): Promise<void> {
  const requestOrigin = route.request().headers()['origin'] || DEFAULT_APP_ORIGIN;
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: {
      'Access-Control-Allow-Origin': requestOrigin,
      'Access-Control-Allow-Credentials': 'true',
      'Cache-Control': 'no-store',
    },
    body: JSON.stringify(body),
  });
}

let report: EndpointContractReport;

test.describe('Frontend endpoint contract and browser smoke', () => {
  test.beforeAll(() => {
    report = compileEndpointContractReport();
  });

  test('all active first-party frontend requests are bound to a backend path and method', async () => {
    expect(report.schemaVersion).toBe('sovereign.frontend-endpoint-contracts.v1');
    expect(report.status).toBe('pass');
    expect(report.revision).toMatch(/^[0-9a-f]{40}$/);
    expect(report.reportSha256).toMatch(/^[0-9a-f]{64}$/);
    expect(report.summary.frontendModuleCount).toBeGreaterThanOrEqual(100);
    expect(report.summary.importEdgeCount).toBeGreaterThanOrEqual(100);
    expect(report.summary.legacyImportViolationCount).toBe(0);
    expect(report.summary.activeRequestCount).toBeGreaterThanOrEqual(50);
    expect(report.summary.boundActiveRequestCount).toBe(report.summary.activeRequestCount);
    expect(report.summary.unmatchedActiveRequestCount).toBe(0);
    expect(report.summary.methodMismatchCount).toBe(0);
    expect(report.summary.methodUnknownCount).toBe(0);
    expect(report.summary.activeMutationRequestCount).toBeGreaterThanOrEqual(1);
    expect(report.summary.activeMutationWithoutTestEvidenceCount).toBe(0);
    expect(report.summary.activeReadRequestCount).toBeGreaterThanOrEqual(1);
    expect(report.summary.activeReadWithoutTestEvidenceCount).toBe(0);
    expect(report.summary.backendRouteCount).toBeGreaterThanOrEqual(100);
    expect(report.summary.externalRequestCount).toBeGreaterThanOrEqual(1);
    expect(report.summary.externalMethodUnknownCount).toBe(0);
    expect(report.errors).toEqual([]);

    const activeRequests = report.bindings.filter(binding => (
      binding.call.active_surface
      && binding.call.source_kind === 'request-call'
      && !binding.call.path.startsWith('/generated/')
    ));
    expect(activeRequests).toHaveLength(report.summary.activeRequestCount);
    for (const binding of activeRequests) {
      expect(binding.status, `${binding.call.method} ${binding.call.path} in ${binding.call.file}`).toBe('BOUND');
      expect(binding.backendRoutes.length, `${binding.call.method} ${binding.call.path}`).toBeGreaterThan(0);
      expect(
        binding.backendRoutes.some(route => route.methods.includes(binding.call.method)),
        `${binding.call.method} ${binding.call.path}`,
      ).toBe(true);
      if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(binding.call.method)) {
        expect(
          binding.testReferences.unit.length
            + binding.testReferences.backend.length
            + binding.testReferences.e2e.length,
          `mutation test evidence for ${binding.call.method} ${binding.call.path}`,
        ).toBeGreaterThan(0);
      }
    }

    expect(report.truthBoundary).toEqual({
      repositoryContractEvidence: true,
      networkRequestsPerformed: false,
      runtimeReachabilityProven: false,
      authenticationProven: false,
      targetEffectProven: false,
      externalTargetReachabilityProven: false,
    });
  });

  test('the built chat-first surface executes the authenticated structured FreeLLM contract without an unconsented billing write', async ({ page }) => {
    const observed: Array<{ method: string; path: string }> = [];
    const unexpectedApiRequests: Array<{ method: string; path: string }> = [];
    const llmChatBodies: Array<Record<string, unknown>> = [];
    const pageErrors: string[] = [];
    const currentUser = {
      id: '00000000-0000-4000-8000-000000000001',
      email: 'endpoint-smoke@example.test',
      displayName: 'Endpoint Smoke',
      role: 'user',
      credits: 9,
      subscriptionStatus: 'free',
      isBanned: false,
      createdAt: 1_700_000_000_000,
    };
    const freeRoute = {
      id: '00000000-0000-4000-8000-000000000777',
      defaultModelId: 'free/test-model',
      label: 'Verified Free Test Route',
      description: 'Chat-first browser smoke',
      provider: 'freellm',
      billingCategory: 'free',
      fundingMode: 'provider_free_quota',
      priority: 1,
      enabled: true,
      capabilities: { codeActionContract: true },
    };

    await page.addInitScript((user) => {
      window.localStorage.setItem('sovereign-user', JSON.stringify({
        state: { user },
        version: 0,
      }));
    }, currentUser);

    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/')) observed.push({ method: request.method(), path: url.pathname });
    });

    await page.route('**/api/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      unexpectedApiRequests.push({ method: request.method(), path: url.pathname });
      await route.fulfill({
        status: 501,
        contentType: 'application/json',
        headers: { 'Cache-Control': 'no-store' },
        body: JSON.stringify({ error: 'unexpected_frontend_endpoint_smoke_request' }),
      });
    });

    await page.route('**/api/auth/me', route => fulfillJson(route, currentUser));
    await page.route('**/api/billing', route => fulfillJson(route, {
      subscription: null,
      invoices: [],
      availablePackages: [],
      packages: [],
    }));
    await page.route('**/api/billing/payment-methods', route => fulfillJson(route, { methods: [] }));
    await page.route('**/api/llm/routes**', route => fulfillJson(route, { routes: [freeRoute] }));
    await page.route('**/api/user/agent/live-workspace/chat-session', async route => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        session: {
          schemaVersion: 'sovereign.live-workspace-chat-session.v1',
          persistence: 'postgresql',
          sessionId: 'livechat-0123456789abcdef01234567',
          repositoryIdentity: typeof body.repositoryIdentity === 'string' ? body.repositoryIdentity : 'UNBOUND',
          repositoryBranch: typeof body.repositoryBranch === 'string' ? body.repositoryBranch : 'main',
          recordedAt: '2026-08-30T00:00:00.000Z',
        },
      });
    });
    await page.route('**/api/user/agent/live-workspace/chat-session/*/mission', async route => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        bubble: {
          schemaVersion: 'sovereign.live-workspace-chat-bubble.v1',
          sessionId: 'livechat-0123456789abcdef01234567',
          clientMessageId: typeof body.clientMessageId === 'string' ? body.clientMessageId : 'mission-endpoint-smoke',
          bubbleKind: 'MISSION_INPUT',
          sourceKind: 'USER_INPUT',
          text: typeof body.text === 'string' ? body.text : '',
          canonicalReferenceHashes: [],
          workflowState: 'RECORDED',
          bubbleHash: '1'.repeat(64),
          recordedAt: '2026-08-30T00:00:01.000Z',
          authoritative: false,
        },
      });
    });
    await page.route('**/api/user/agent/jobs**', route => fulfillJson(route, { jobs: [] }));
    await page.route('**/api/toolchain/user-tools', route => fulfillJson(route, {
      tools: [],
      allowed_repos: [],
      rules: {
        auto_load: true,
        github_read: 'after_login',
        auto_write: false,
        push_to_main: false,
        pr_mode: 'draft_only',
        confirm_required: true,
        audit_log: true,
      },
    }));
    await page.route('**/api/toolchain/universal/manifest', route => fulfillJson(route, {
      version: 'endpoint-smoke-v1',
      runtime: 'browser',
      tools: [],
      policy: {
        arbitraryShell: false,
        directProductionRunner: false,
      },
    }));
    await page.route('**/api/toolchain/skills/list', route => fulfillJson(route, { skills: [] }));
    await page.route('**/health/ready', route => fulfillJson(route, { ok: true, configured: true }));
    await page.route('**/api/llm/chat', async route => {
      llmChatBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      await fulfillJson(route, {
        model: freeRoute.defaultModelId,
        outputContract: {
          id: 'sovereign-code-action-v1',
          validated: true,
        },
        choices: [{
          message: {
            content: JSON.stringify({
              mode: 'clarify',
              intent: 'unknown',
              action_disposition: 'review',
              clarification_code: 'repo_required',
              is_startup: false,
              confidence: 0.96,
              language: 'de',
            }),
          },
        }],
      });
    });

    await page.goto('/');
    const app = page.locator('[data-testid="sovereign-chat-app"]');
    await expect(app).toBeVisible({ timeout: 30_000 });
    await expect(app).toHaveAttribute('data-layout', 'chat-first-agent-zero-background');
    await expect(page.locator('[data-layout="chat-primary-agent-zero-background"]')).toBeVisible();
    await expect(page.locator('[data-testid="sovereign-chat-primary"]')).toBeVisible();
    await expect(page.locator('[data-testid="sovereign-chat-body-window"]')).toBeVisible();
    await expect(page.locator('[data-testid="live-workspace-monitor-desktop"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="sovereign-chat-dock"]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Menü', exact: true })).toBeVisible();

    const routeTrigger = page.locator('[data-testid="sovereign-llm-route-picker-trigger"]');
    await expect(routeTrigger).toBeVisible();
    await expect(routeTrigger).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByText('Verified Free Test Route')).toHaveCount(0);
    await routeTrigger.click();
    await expect(page.getByRole('dialog', { name: 'LLM-Modell auswählen' })).toBeVisible();
    await expect(page.getByRole('option', { name: /Verified Free Test Route/ })).toBeVisible();
    await page.keyboard.press('Escape');

    const coverageResponse = await page.request.get('/generated/test-coverage-map.json');
    expect(coverageResponse.status()).toBe(200);
    const coveragePayload = await coverageResponse.json() as {
      schemaVersion?: string;
      totalTestFiles?: number;
      testRoots?: Record<string, number>;
      files?: Array<{ file?: string }>;
    };
    expect(coveragePayload.schemaVersion).toBe('sovereign.test-coverage-map.v2');
    expect(coveragePayload.totalTestFiles).toBeGreaterThan(0);
    expect(coveragePayload.files).toHaveLength(coveragePayload.totalTestFiles);
    const publishedTestPaths = new Set((coveragePayload.files ?? []).map((entry) => entry.file));
    for (const representative of [
      'src/App.test.tsx',
      'backend/tests/test_agent_runtime_routes.py',
      'scripts/tests/test_frontend_test_gate.py',
      'tests/e2e/frontend-endpoint-contract-smoke.spec.ts',
    ]) {
      expect(publishedTestPaths.has(representative)).toBe(true);
    }
    for (const root of ['src', 'backend/tests', 'scripts/tests', 'tests/e2e']) {
      expect(coveragePayload.testRoots?.[root]).toBeGreaterThan(0);
    }

    const composer = page.getByLabel('Codeauftrag an Sovereign');
    await composer.fill('Bitte repariere den Build und führe noch nichts ohne Freigabe aus.');
    await composer.press('Enter');
    await expect(page.getByText('Welches Repository soll ich ändern?')).toBeVisible({ timeout: 10_000 });

    await expect.poll(() => observed.some(item => item.method === 'GET' && item.path === '/api/auth/me')).toBe(true);
    await expect.poll(() => observed.some(item => item.method === 'GET' && item.path === '/api/llm/routes')).toBe(true);
    await expect.poll(() => observed.some(item => item.method === 'POST' && item.path === '/api/llm/chat')).toBe(true);

    expect(llmChatBodies).toHaveLength(1);
    expect(llmChatBodies[0]).toMatchObject({
      outputContractId: 'sovereign-code-action-v1',
      routeSelectionMode: 'auto',
      model: freeRoute.id,
      stream: false,
    });
    expect(Array.isArray(llmChatBodies[0]?.messages)).toBe(true);

    const billingWrites = observed.filter(item => item.path.startsWith('/api/billing') && item.method !== 'GET');
    expect(billingWrites).toEqual([]);
    expect(observed.some(item => item.path === '/api/billing/cancel')).toBe(false);
    expect(observed.some(item => item.path === '/api/billing/restore')).toBe(false);
    expect(unexpectedApiRequests).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
});
