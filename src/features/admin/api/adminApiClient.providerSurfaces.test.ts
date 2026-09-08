import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  adminApiClient,
  clearAdminKey,
  isAcceptedLlmProviderSurfaceReadModel,
  setAdminKey,
} from './adminApiClient';

afterEach(() => {
  clearAdminKey();
  vi.unstubAllGlobals();
});

describe('adminApiClient typed provider surface read model', () => {
  it('reads paid, OpenRouter-free, and FreeLLMAPI provider evidence from their dedicated endpoints', async () => {
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
          minimumReadyRoutes: 7,
          providers: useNonCanonicalEnvelope ? [
            {
              id: 'freellmapi-source',
              sourceType: 'freellmapi-direct',
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
            },
            {
              id: 'freellmpool-source',
              sourceType: 'freellmpool-private',
              label: 'FreeLLMPool 0.11.4',
              apiBase: 'http://freellmpool:8080/v1',
              modelsUrl: null,
              authMode: 'managed-bearer',
              keyHint: null,
              status: 'healthy',
              lastHttpStatus: 200,
              lastErrorCode: null,
              lastDiscoveredAt: null,
              lastCheckedAt: null,
              enabled: true,
              ownerRequestId: null,
              models: [],
            },
          ] : [],
        },
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
            accountWideQuotaScope: 'openrouter:account:free-models',
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

    expect(result.freeRevolverMinimumReadyRoutes).toBe(7);
    expect(result.openRouterPaid?.selectableModels).toBe(291);
    expect(result.openRouterFree?.routingPolicy.paidFallbackAllowed).toBe(false);
    expect(calls.sort()).toEqual([
      '/api/admin/llm/openrouter/free/status',
      '/api/admin/llm/openrouter/status',
      '/api/admin/llm/revolver-v3/providers',
    ]);

    useNonCanonicalEnvelope = true;
    const recovered = await adminApiClient.getLlmProviderSurfaceReadModel();
    expect(recovered.freeRevolverMinimumReadyRoutes).toBe(7);
    expect(recovered.providers).toHaveLength(2);
    expect(recovered.providers[0]).toMatchObject({
      providerSurfaceKind: 'free-revolver',
      lifecycle: 'active',
      canonicalAction: 'revolver-discover',
      enabled: true,
    });
    expect(recovered.providers[1]).toMatchObject({
      providerSurfaceKind: 'retired-reference',
      lifecycle: 'historical',
      canonicalAction: 'none',
      enabled: false,
    });
  });

  it('keeps Free Revolver visible when adjacent provider surfaces are stale or non-canonical', async () => {
    setAdminKey('test-admin-key');

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input)).pathname;
      const payloadByPath: Record<string, unknown> = {
        '/api/admin/llm/revolver-v3/providers': {
          ok: true,
          truthOwner: 'legacy-envelope',
          keyStorage: 'legacy-envelope',
          activationRule: 'legacy-envelope',
          minimumReadyRoutes: 7,
          providers: [{
            id: 'freellmapi-source',
            sourceType: 'freellmapi-direct',
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
          }],
        },
        '/api/admin/llm/openrouter/status': { status: 'legacy' },
        '/api/admin/llm/openrouter/free/status': { ok: false },
      };
      return new Response(JSON.stringify(payloadByPath[path]), {
        status: payloadByPath[path] ? 200 : 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    const result = await adminApiClient.getLlmProviderSurfaceReadModel();

    expect(result.freeRevolverMinimumReadyRoutes).toBe(7);
    expect(result.providers).toHaveLength(1);
    expect(result.providers[0]).toMatchObject({
      id: 'freellmapi-source',
      providerSurfaceKind: 'free-revolver',
      lifecycle: 'active',
      canonicalAction: 'revolver-discover',
      enabled: true,
    });
    expect(result.openRouterPaid).toBeNull();
    expect(result.openRouterFree).toBeNull();
    expect(isAcceptedLlmProviderSurfaceReadModel(result)).toBe(true);
  });

  it('normalizes a persisted OmniRoute source as historical and non-actionable', () => {
    expect(isAcceptedLlmProviderSurfaceReadModel({
      providers: [{
        id: 'legacy-omniroute',
        sourceType: 'omniroute',
        label: 'OmniRoute (retired)',
        apiBase: 'http://omniroute:20128/v1',
        providerSurfaceKind: 'retired-reference',
        lifecycle: 'historical',
        canonicalAction: 'none',
        modelsUrl: null,
        authMode: 'none',
        keyHint: null,
        status: 'disabled',
        lastHttpStatus: null,
        lastErrorCode: 'omniroute_retired_owner_simplification',
        lastDiscoveredAt: null,
        lastCheckedAt: null,
        enabled: false,
        ownerRequestId: null,
        models: [],
      }],
      freeRevolverMinimumReadyRoutes: 7,
      openRouterPaid: null,
      openRouterFree: null,
    })).toBe(true);
  });

  it('fails closed when a provider readback pairs a surface with a non-canonical action', () => {
    expect(isAcceptedLlmProviderSurfaceReadModel({
      providers: [{
        providerSurfaceKind: 'retired-reference',
        lifecycle: 'historical',
        canonicalAction: 'revolver-discover',
      }],
      freeRevolverMinimumReadyRoutes: 7,
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
          accountWideQuotaScope: 'openrouter:account:free-models',
        },
        runtimeIdentity: {},
        secretValuesReturned: false,
      },
    } as never)).toBe(false);
  });

  it('rejects truncated, wrong-identity, secret-bearing, and paid-fallback readbacks', () => {
    const valid = {
      providers: [],
      freeRevolverMinimumReadyRoutes: 7,
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
          accountWideQuotaScope: 'openrouter:account:free-models',
        },
        runtimeIdentity: {},
        secretValuesReturned: false,
      },
    };

    expect(isAcceptedLlmProviderSurfaceReadModel(valid)).toBe(true);
    const staleQuotaScope = structuredClone(valid);
    staleQuotaScope.openRouterFree.routingPolicy.accountWideQuotaScope = 'openrouter-free';
    expect(isAcceptedLlmProviderSurfaceReadModel(staleQuotaScope)).toBe(false);

    expect(isAcceptedLlmProviderSurfaceReadModel({
      providers: [],
      freeRevolverMinimumReadyRoutes: 7,
      openRouterPaid: { transport: 'openrouter' },
      openRouterFree: { routingPolicy: { paidFallbackAllowed: false } },
    })).toBe(false);

    const secretBearingPaid = structuredClone(valid);
    secretBearingPaid.openRouterPaid.secretValuesReturned = true;
    expect(isAcceptedLlmProviderSurfaceReadModel(secretBearingPaid)).toBe(false);

    const paidFallback = structuredClone(valid);
    paidFallback.openRouterFree.routingPolicy.paidFallbackAllowed = true;
    expect(isAcceptedLlmProviderSurfaceReadModel(paidFallback)).toBe(false);
  });
});
