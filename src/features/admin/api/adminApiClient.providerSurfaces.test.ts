import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  adminApiClient,
  clearAdminKey,
  isAcceptedLlmProviderSurfaceReadModel,
  setAdminKey,
} from './adminApiClient';

const omniRoute = {
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
};

afterEach(() => {
  clearAdminKey();
  vi.unstubAllGlobals();
});

describe('adminApiClient typed provider surface read model', () => {
  it('reads paid, free, OmniRoute, and generic provider evidence from their dedicated endpoints', async () => {
    const calls: string[] = [];
    let useNonCanonicalEnvelope = false;
    setAdminKey('test-admin-key');

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input)).pathname;
      calls.push(path);
      const payloadByPath: Record<string, unknown> = {
        '/api/admin/llm/revolver-v3/providers': {
          ok: true,
          truthOwner: useNonCanonicalEnvelope
            ? 'backend'
            : 'postgresql-owner-input-direct-freellm',
          keyStorage: 'owner-managed-direct-freellm',
          activationRule: 'managed-free-quota-plus-revision-bound-double-canary-without-positive-cost-contradiction',
          providers: [],
        },
        '/api/admin/llm/omniroute/status': omniRoute,
        '/api/admin/llm/openrouter/status': {
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
        },
        '/api/admin/llm/openrouter/free/status': {
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
            accountWideQuotaScope: 'openrouter-free',
          },
          runtimeIdentity: {},
          secretValuesReturned: false,
        },
      };
      return new Response(JSON.stringify(payloadByPath[path]), {
        status: payloadByPath[path] ? 200 : 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    const result = await adminApiClient.getLlmProviderSurfaceReadModel();

    expect(result.omniRoute).toEqual(omniRoute);
    expect(result.openRouterPaid.selectableModels).toBe(291);
    expect(result.openRouterFree.routingPolicy.paidFallbackAllowed).toBe(false);
    expect(calls.sort()).toEqual([
      '/api/admin/llm/omniroute/status',
      '/api/admin/llm/openrouter/free/status',
      '/api/admin/llm/openrouter/status',
      '/api/admin/llm/revolver-v3/providers',
    ]);

    useNonCanonicalEnvelope = true;
    await expect(adminApiClient.getLlmProviderSurfaceReadModel())
      .rejects.toThrow('Free-Provider-Readback verletzt die kanonische typisierte Aktionsgrenze.');
  });

  it('sends the only accepted OmniRoute mutation to its dedicated runtime endpoint', async () => {
    const calls: Array<{ path: string; method: string }> = [];
    setAdminKey('test-admin-key');

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({
        path: new URL(String(input)).pathname,
        method: init?.method ?? 'GET',
      });
      return new Response(JSON.stringify(omniRoute), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    await adminApiClient.refreshOmniRoute();

    expect(calls).toEqual([
      { path: '/api/admin/llm/omniroute/refresh', method: 'POST' },
    ]);
  });

  it('fails closed when a provider readback pairs a surface with a non-canonical action', () => {
    expect(isAcceptedLlmProviderSurfaceReadModel({
      providers: [{
        providerSurfaceKind: 'omniroute-auto',
        lifecycle: 'active',
        canonicalAction: 'revolver-discover',
      }],
      omniRoute,
      openRouterPaid: {
        status: 'ready',
        deploymentStatus: 'ready',
        routeId: 'openrouter-root',
        transport: 'openrouter',
        keyStored: true,
        keyHint: '…paid',
        selectableModels: 1,
        lastCanaryRequestId: null,
        lastCanaryAt: null,
        lastErrorCode: null,
        secretValuesReturned: false,
      },
      openRouterFree: {
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
          accountWideQuotaScope: 'openrouter-free',
        },
        runtimeIdentity: {},
        secretValuesReturned: false,
      },
    } as never)).toBe(false);
  });

  it('rejects truncated, wrong-identity, secret-bearing, and paid-fallback readbacks', () => {
    const valid = {
      providers: [],
      omniRoute,
      openRouterPaid: {
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
      },
      openRouterFree: {
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
          accountWideQuotaScope: 'openrouter-free',
        },
        runtimeIdentity: {},
        secretValuesReturned: false,
      },
    };

    expect(isAcceptedLlmProviderSurfaceReadModel(valid)).toBe(true);

    const readyOmniRoute = {
      ...omniRoute,
      ok: true,
      disabled: false,
      activationState: 'ready',
      blocker: null,
      confirmationCount: 2,
      receiptSha256: 'c'.repeat(64),
    };
    expect(isAcceptedLlmProviderSurfaceReadModel({
      ...valid,
      omniRoute: readyOmniRoute,
    })).toBe(true);
    expect(isAcceptedLlmProviderSurfaceReadModel({
      ...valid,
      omniRoute: { ...readyOmniRoute, receiptSha256: null },
    })).toBe(false);
    expect(isAcceptedLlmProviderSurfaceReadModel({
      ...valid,
      omniRoute: { ...readyOmniRoute, blocker: 'omniroute_canary_http_503' },
    })).toBe(false);

    expect(isAcceptedLlmProviderSurfaceReadModel({
      providers: [],
      omniRoute: { routeSource: 'omniroute' },
      openRouterPaid: { transport: 'openrouter' },
      openRouterFree: { routingPolicy: { paidFallbackAllowed: false } },
    })).toBe(false);

    const wrongOmniRoute = structuredClone(valid);
    wrongOmniRoute.omniRoute.routeId = 'wrong-route';
    expect(isAcceptedLlmProviderSurfaceReadModel(wrongOmniRoute)).toBe(false);

    const secretBearingPaid = structuredClone(valid);
    secretBearingPaid.openRouterPaid.secretValuesReturned = true;
    expect(isAcceptedLlmProviderSurfaceReadModel(secretBearingPaid)).toBe(false);

    const paidFallback = structuredClone(valid);
    paidFallback.openRouterFree.routingPolicy.paidFallbackAllowed = true;
    expect(isAcceptedLlmProviderSurfaceReadModel(paidFallback)).toBe(false);
  });
});
