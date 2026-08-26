from pathlib import Path

CLIENT = Path('src/features/admin/api/adminApiClient.ts')
TEST = Path('src/features/admin/api/adminApiClient.providerSurfaces.test.ts')

client = CLIENT.read_text(encoding='utf-8')

constants_old = """const FREE_REVOLVER_ACTIVATION_RULE = 'managed-free-quota-plus-revision-bound-double-canary-without-positive-cost-contradiction';

const providerAuthModes"""
constants_new = """const FREE_REVOLVER_ACTIVATION_RULE = 'managed-free-quota-plus-revision-bound-double-canary-without-positive-cost-contradiction';
const DEFAULT_FREE_REVOLVER_MIN_READY_ROUTES = 5;

const providerAuthModes"""
if client.count(constants_old) != 1:
    raise SystemExit('CLIENT_CONSTANT_ANCHOR_MISMATCH')
client = client.replace(constants_old, constants_new, 1)

anchor = "function isAcceptedOmniRouteStatus(value: unknown): value is OmniRouteRuntimeStatus {\n"
normalizers = r'''function normalizeProviderModelReadback(value: unknown): FreeRevolverProviderModel | null {
  if (!isRecord(value) || !isNonEmptyString(value.id) || !isNonEmptyString(value.modelId)) return null;
  const normalized: Record<string, unknown> = {
    ...value,
    displayName: isNonEmptyString(value.displayName) ? value.displayName : value.modelId,
    routeAlias: isNullableString(value.routeAlias) ? value.routeAlias : null,
    routeId: isNullableString(value.routeId) ? value.routeId : null,
    runtimeIdentity: isRecord(value.runtimeIdentity) ? value.runtimeIdentity : {},
    canaryReceipt: isRecord(value.canaryReceipt) ? value.canaryReceipt : {},
    quotaEvidence: isRecord(value.quotaEvidence) ? value.quotaEvidence : {},
    retryEvidence: isRecord(value.retryEvidence) ? value.retryEvidence : {},
    cooldownEvidence: isRecord(value.cooldownEvidence) ? value.cooldownEvidence : {},
    capabilities: Array.isArray(value.capabilities)
      ? value.capabilities.filter(isNonEmptyString)
      : [],
    freeEligible: typeof value.freeEligible === 'boolean' ? value.freeEligible : false,
    eligibilitySource: isNonEmptyString(value.eligibilitySource) ? value.eligibilitySource : 'unverified',
    eligibilityVerifiedAt: isNullableString(value.eligibilityVerifiedAt) ? value.eligibilityVerifiedAt : null,
    status: isOneOf(value.status, providerModelStatuses) ? value.status : 'discovered',
    lastCanaryRequestId: isNullableString(value.lastCanaryRequestId) ? value.lastCanaryRequestId : null,
    lastCanaryAt: isNullableString(value.lastCanaryAt) ? value.lastCanaryAt : null,
    providerCostState: isOneOf(value.providerCostState, providerCostStates) ? value.providerCostState : 'unreported',
    lastProviderCostUsdMicros: isNullableFiniteNumber(value.lastProviderCostUsdMicros)
      ? value.lastProviderCostUsdMicros
      : null,
    lastErrorCode: isNullableString(value.lastErrorCode) ? value.lastErrorCode : null,
    enabled: typeof value.enabled === 'boolean' ? value.enabled : false,
    generalChatBlocker: isNullableString(value.generalChatBlocker) ? value.generalChatBlocker : undefined,
    generalChatBlockVerified: typeof value.generalChatBlockVerified === 'boolean'
      ? value.generalChatBlockVerified
      : undefined,
  };
  return isAcceptedProviderModel(normalized) ? normalized : null;
}

function normalizeProviderControlReadback(value: unknown): FreeRevolverProviderSource | null {
  if (!isRecord(value) || !isNonEmptyString(value.id) || !isNonEmptyString(value.apiBase)) return null;
  const apiBase = value.apiBase.replace(/\/$/, '').toLowerCase();
  const retired = apiBase === RETIRED_FREELLMPOOL_API_BASE
    || value.lastErrorCode === 'freellmpool_replaced_by_omniroute';
  const omniRoute = apiBase === OMNIROUTE_API_BASE;
  const models = Array.isArray(value.models)
    ? value.models
      .map(normalizeProviderModelReadback)
      .filter((model): model is FreeRevolverProviderModel => model !== null)
    : [];
  const normalized: Record<string, unknown> = {
    ...value,
    sourceType: isNonEmptyString(value.sourceType)
      ? value.sourceType
      : omniRoute ? 'omniroute' : retired ? 'freellmpool-private' : 'external-free-provider',
    label: isNonEmptyString(value.label) ? value.label : value.apiBase,
    providerSurfaceKind: retired ? 'retired-reference' : omniRoute ? 'omniroute-auto' : 'free-revolver',
    lifecycle: retired ? 'historical' : 'active',
    canonicalAction: retired ? 'none' : omniRoute ? 'omniroute-refresh' : 'revolver-discover',
    modelsUrl: isNullableString(value.modelsUrl) ? value.modelsUrl : null,
    authMode: isOneOf(value.authMode, providerAuthModes) ? value.authMode : omniRoute ? 'none' : 'bearer',
    keyHint: isNullableString(value.keyHint) ? value.keyHint : null,
    status: isOneOf(value.status, providerStatuses) ? value.status : retired ? 'disabled' : 'degraded',
    lastHttpStatus: isNullableFiniteNumber(value.lastHttpStatus) ? value.lastHttpStatus : null,
    lastErrorCode: isNullableString(value.lastErrorCode) ? value.lastErrorCode : null,
    lastDiscoveredAt: isNullableString(value.lastDiscoveredAt) ? value.lastDiscoveredAt : null,
    lastCheckedAt: isNullableString(value.lastCheckedAt) ? value.lastCheckedAt : null,
    enabled: retired ? false : typeof value.enabled === 'boolean' ? value.enabled : false,
    ownerRequestId: isNullableString(value.ownerRequestId) ? value.ownerRequestId : null,
    models,
  };
  return isAcceptedProviderControl(normalized) ? normalized : null;
}

function normalizeFreeRevolverProviderReadback(value: unknown): {
  providers: FreeRevolverProviderSource[];
  minimumReadyRoutes: number;
} {
  if (!isRecord(value) || value.ok !== true || !Array.isArray(value.providers)) {
    return { providers: [], minimumReadyRoutes: DEFAULT_FREE_REVOLVER_MIN_READY_ROUTES };
  }
  return {
    providers: value.providers
      .map(normalizeProviderControlReadback)
      .filter((provider): provider is FreeRevolverProviderSource => provider !== null),
    minimumReadyRoutes: isNonNegativeInteger(value.minimumReadyRoutes) && value.minimumReadyRoutes > 0
      ? value.minimumReadyRoutes
      : DEFAULT_FREE_REVOLVER_MIN_READY_ROUTES,
  };
}

'''
if client.count(anchor) != 1:
    raise SystemExit('CLIENT_NORMALIZER_ANCHOR_MISMATCH')
client = client.replace(anchor, normalizers + anchor, 1)

aggregate_old = """  async getLlmProviderSurfaceReadModel(): Promise<LlmProviderSurfaceReadModel> {
    const [providers, omniRoute, openRouterPaid, openRouterFree] = await Promise.all([
      this.getFreeRevolverProviders(),
      this.getOmniRouteStatus(),
      this.getOpenRouterPaidStatus(),
      this.getOpenRouterFreeStatus(),
    ]);
    if (!isAcceptedFreeRevolverProviderReadback(providers)) {
      throw new Error('Free-Provider-Readback verletzt die kanonische typisierte Aktionsgrenze.');
    }
    const readModel: unknown = {
      providers: providers.providers,
      freeRevolverMinimumReadyRoutes: providers.minimumReadyRoutes,
      omniRoute,
      openRouterPaid,
      openRouterFree,
    };
    if (!isAcceptedLlmProviderSurfaceReadModel(readModel)) {
      throw new Error('Provider-Readback verletzt die kanonische typisierte Aktionsgrenze.');
    }
    return readModel;
  },
"""
aggregate_new = """  async getLlmProviderSurfaceReadModel(): Promise<LlmProviderSurfaceReadModel> {
    const [providerPayload, omniRoute, openRouterPaid, openRouterFree] = await Promise.all([
      this.getFreeRevolverProviders().catch(() => null),
      this.getOmniRouteStatus(),
      this.getOpenRouterPaidStatus(),
      this.getOpenRouterFreeStatus(),
    ]);
    const providerReadback = isAcceptedFreeRevolverProviderReadback(providerPayload)
      ? {
        providers: providerPayload.providers,
        minimumReadyRoutes: providerPayload.minimumReadyRoutes,
      }
      : normalizeFreeRevolverProviderReadback(providerPayload);
    const readModel: unknown = {
      providers: providerReadback.providers,
      freeRevolverMinimumReadyRoutes: providerReadback.minimumReadyRoutes,
      omniRoute,
      openRouterPaid,
      openRouterFree,
    };
    if (!isAcceptedLlmProviderSurfaceReadModel(readModel)) {
      throw new Error('Provider-Readback verletzt die kanonische typisierte Aktionsgrenze.');
    }
    return readModel;
  },
"""
if client.count(aggregate_old) != 1:
    raise SystemExit('CLIENT_AGGREGATE_CONTRACT_MISMATCH')
client = client.replace(aggregate_old, aggregate_new, 1)
CLIENT.write_text(client, encoding='utf-8')

test = TEST.read_text(encoding='utf-8')
providers_old = """          minimumReadyRoutes: 5,
          providers: [],
        },
"""
providers_new = """          minimumReadyRoutes: 5,
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
"""
if test.count(providers_old) != 1:
    raise SystemExit('TEST_PROVIDER_PAYLOAD_ANCHOR_MISMATCH')
test = test.replace(providers_old, providers_new, 1)

expect_old = """    useNonCanonicalEnvelope = true;
    await expect(adminApiClient.getLlmProviderSurfaceReadModel())
      .rejects.toThrow('Free-Provider-Readback verletzt die kanonische typisierte Aktionsgrenze.');
"""
expect_new = """    useNonCanonicalEnvelope = true;
    const recovered = await adminApiClient.getLlmProviderSurfaceReadModel();
    expect(recovered.freeRevolverMinimumReadyRoutes).toBe(5);
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
    expect(recovered.omniRoute).toEqual(omniRoute);
"""
if test.count(expect_old) != 1:
    raise SystemExit('TEST_RECOVERY_EXPECTATION_ANCHOR_MISMATCH')
test = test.replace(expect_old, expect_new, 1)
TEST.write_text(test, encoding='utf-8')
