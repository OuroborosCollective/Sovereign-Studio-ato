/**
 * adminApiClient — Real HTTP client for sovereign-backend admin API.
 *
 * Base URL resolved from VITE_ADMIN_API_BASE env var (set in CI and .env).
 * Auth: Authorization: Bearer <admin-api-key> kept only in module memory.
 * Flask returns camelCase via SQL AS-aliases — all types here are camelCase.
 *
 * Issue #460
 */

// Resolved at build time by Vite; falls back to production URL.
export const ADMIN_API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

let adminKeyInMemory = '';

// ── Types ─────────────────────────────────────────────────────────────────────

export type UserRole = 'user' | 'admin' | 'superadmin';
export type SubscriptionStatus = 'active' | 'canceled' | 'past_due' | 'trialing' | 'free';

export interface AdminUser {
  id: string;
  email: string;
  displayName: string;
  role: UserRole;
  credits: number;
  subscriptionStatus: SubscriptionStatus;
  isBanned: boolean;
  createdAt: string;
  lastActiveAt: string | null;
}

export interface Transaction {
  id: string;
  userId: string | null;
  userEmail: string;
  type: 'credit_purchase' | 'subscription' | 'refund' | 'adjustment' | 'usage';
  amount: number;
  currency: string;
  status: 'completed' | 'pending' | 'failed' | 'refunded';
  description: string;
  createdAt: string;
}

export interface BillingStats {
  mrr: number;
  activeSubscriptions: number;
  totalCredits: number;
  totalRevenue: number;
  churnRate: number;
}

export interface LauncherToolOverride {
  id: string;
  label: string;
  disabled: boolean;
  badge: 'NEU' | 'BETA' | 'PRO' | null;
  sortOrder: number;
}

export type LlmBillingCategory = 'free' | 'standard' | 'premium';

export interface LlmRevolverState {
  status: 'ready' | 'cooldown' | 'blocked';
  consecutiveFailures: number;
  cooldownUntil: string | null;
  lastHttpStatus: number | null;
  lastBlocker: string | null;
  lastAttemptAt: string | null;
}

export interface LlmRoute {
  id: string;
  modelId: string;
  modelName: string;
  provider: string;
  creditsPerUnit: number;
  disabled: boolean;
  priority: number;
  billingCategory: LlmBillingCategory;
  markupMultiplier: number;
  minimumMultiplier: number;
  inputUsdPerMillion: number | null;
  cachedInputUsdPerMillion: number | null;
  outputUsdPerMillion: number | null;
  pricingVerified: boolean;
  pricingSource: string;
  revolverEligible: boolean;
  quotaScope: string;
  revolverState: LlmRevolverState;
  policyBlocker: string | null;
}

export interface LlmBillingCategoryOption {
  id: LlmBillingCategory;
  minimumMultiplier: number;
  revolverOnly: boolean;
}

export interface LlmRevolverStats {
  attempts24h: number;
  successes24h: number;
  rotations24h: number;
  blockedOrCoolingScopes: number;
}

export interface LlmRevolverV3Status {
  runtime: 'postgresql-litellm-evidence';
  profile: {
    profileKey?: string;
    mode?: 'sequential' | 'weighted' | 'race';
    raceN?: number;
    timeoutMs?: number;
    tokenBudget?: number;
    requiredCapabilities?: string[];
    structuredRepairAttempts?: number;
    semanticCacheEnabled?: boolean;
    revision?: number;
  };
  structuredOutput24h: { checks: number; valid: number; invalid: number };
  semanticCachePolicy: 'cache_safe-only';
  autoWeights: 'recommendation-only';
  pricingEvidenceTtlHours: number;
}

export type FreeRevolverProviderAuthMode = 'bearer' | 'x-api-key' | 'none';
export type FreeRevolverProviderStatus =
  | 'awaiting_owner_input' | 'probing' | 'healthy' | 'degraded'
  | 'blocked' | 'disabled';

export interface FreeRevolverProviderModel {
  id: string;
  modelId: string;
  displayName: string;
  litellmAlias: string | null;
  capabilities: string[];
  freeVerified: boolean;
  pricingSource: string;
  pricingVerifiedAt: string | null;
  status: 'discovered' | 'ready' | 'blocked' | 'disabled';
  lastCanaryRequestId: string | null;
  lastCanaryAt: string | null;
  canaryCostState: 'zero' | 'unreported' | 'nonzero';
  lastProviderCostUsdMicros: number | null;
  lastErrorCode: string | null;
  enabled: boolean;
}

export interface FreeRevolverProviderSource {
  id: string;
  label: string;
  apiBase: string;
  modelsUrl: string | null;
  authMode: FreeRevolverProviderAuthMode;
  keyHint: string | null;
  status: FreeRevolverProviderStatus;
  lastHttpStatus: number | null;
  lastErrorCode: string | null;
  lastDiscoveredAt: string | null;
  lastCheckedAt: string | null;
  enabled: boolean;
  ownerRequestId: string | null;
  models: FreeRevolverProviderModel[];
}

export interface LlmModelCatalogEntry {
  modelId: string;
  providerModel: string;
  provider: string | null;
  inputUsdPerMillion: number | null;
  cachedInputUsdPerMillion: number | null;
  outputUsdPerMillion: number | null;
  pricingVerified: boolean;
  pricingSource: string;
  freeEligible: boolean;
}

export type LlmRouteUpdate = Partial<Pick<
  LlmRoute,
  'disabled' | 'priority' | 'billingCategory' | 'markupMultiplier' | 'quotaScope'
>>;

export interface AuditEntry {
  id: string;
  adminId: string;
  adminEmail: string;
  action: string;
  targetId: string | null;
  changes: Record<string, unknown>;
  createdAt: string;
}

export type PaymentMethodType =
  | 'paypal' | 'skrill'
  | 'crypto_btc' | 'crypto_eth' | 'crypto_usdt'
  | 'google_play';

export interface PaymentMethod {
  id: string;
  type: PaymentMethodType | string;
  label: string;
  enabled: boolean;
  config: Record<string, unknown>;
  updatedAt: string;
}

export interface CreditPackage {
  id: string;
  name: string;
  credits: number;
  priceEur: number;
  description: string | null;
  enabled: boolean;
  sortOrder: number;
}

export type EnterprisePlatformStatus =
  | 'verified'
  | 'degraded'
  | 'blocked'
  | 'defined_not_run'
  | 'isolated';

export interface EnterpriseRuntimeIdentity {
  runtimeId: string;
  startedAt: string;
  sourceRevision: string;
  sourceRevisionVerified: boolean;
  imageDigest: string;
  imageDigestVerified: boolean;
  environment: string;
}

export interface EnterpriseIntegration {
  id: string;
  label: string;
  status: EnterprisePlatformStatus;
  required: boolean;
  boundary: string;
  evidence: Record<string, unknown>;
  blocker: string | null;
  latencyMs: number | null;
  checkedAt: string;
}

export interface EnterpriseStatistics {
  status: EnterprisePlatformStatus;
  users: { total: number; active30d: number; banned: number } | null;
  agents: { total: number; completed: number; blockedOrFailed: number } | null;
  knowledge: {
    sources: number;
    vectors: number;
    pgvectorVectors: number;
    milvusProjected: number;
    milvusIndexed: number;
    milvusPending: number;
    milvusSyncing: number;
    milvusBlocked: number;
    milvusKnowledgeBlocks: number;
    milvusAgentPatterns: number;
  } | null;
  llm24h: {
    requests: number;
    tokens: number;
    providerCostUsd: number;
    activeRoutes: number;
  } | null;
  evidence: { total: number; latestAt: string | null } | null;
  database: { latestMigration: number } | null;
  calculatedAt: string;
  blocker?: string;
}

export interface EnterprisePlatformOverview {
  ok: boolean;
  status: EnterprisePlatformStatus;
  schemaVersion: string;
  mode: 'PROTOTYPE_TO_PLATFORM';
  requestId: string;
  runtime: EnterpriseRuntimeIdentity;
  statistics: EnterpriseStatistics;
  integrations: EnterpriseIntegration[];
  generatedAt: string;
  truthNotice: string;
}

export interface EnterpriseEvidenceReceipt {
  id: string;
  requestId: string;
  actorId: string | null;
  scope: 'readiness' | 'completion';
  status: EnterprisePlatformStatus;
  sourceRevision: string;
  runtimeIdentity: string;
  evidenceSha256: string;
  evidence: Record<string, unknown>;
  observedAt: string;
}

export interface EnterpriseCanaryResult {
  ok: boolean;
  status: EnterprisePlatformStatus;
  requestId: string;
  scope: 'readiness' | 'completion';
  evidence: Record<string, unknown>;
  receipt: {
    id: string;
    evidenceSha256: string;
    observedAt: string;
    readbackVerified: true;
  };
}

// ── Key management ────────────────────────────────────────────────────────────

export function getAdminKey(): string {
  return adminKeyInMemory;
}
export function setAdminKey(key: string): void {
  adminKeyInMemory = key.trim();
}
export function clearAdminKey(): void {
  adminKeyInMemory = '';
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function req<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 15_000,
): Promise<T> {
  const key = getAdminKey();
  if (!key) throw new Error('Admin-API-Key fehlt. Bitte im Panel eintragen.');

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${ADMIN_API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      credentials: 'omit',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        Authorization: `Bearer ${key}`,
        ...(options.headers ?? {}),
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`Backend-Zeitüberschreitung nach ${Math.ceil(timeoutMs / 1000)} Sekunden.`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }

  if (!res.ok) {
    if (res.status === 401 || res.status === 403) clearAdminKey();
    const body = await res.json().catch(() => ({})) as {
      error?: string | { message?: string; code?: string };
      message?: string;
    };
    const message = typeof body.error === 'string'
      ? body.error
      : body.error?.message ?? body.message;
    throw new Error(message ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function resolveProtectedOwnerInput(
  requestId: string,
  protectedValue: string,
): Promise<{ ok: true; status: 'consumed'; targetId: string }> {
  const key = getAdminKey();
  if (!key) throw new Error('Admin-API-Key fehlt. Bitte im Panel eintragen.');
  const encoded = new TextEncoder().encode(protectedValue);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(
      `${ADMIN_API_BASE}/api/admin/owner-input/requests/${encodeURIComponent(requestId)}/resolve?decision=yes`,
      {
        method: 'POST',
        signal: controller.signal,
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/octet-stream',
          Authorization: `Bearer ${key}`,
        },
        body: encoded,
      },
    );
    const body = await response.json().catch(() => ({})) as { error?: string; status?: string; targetId?: string };
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) clearAdminKey();
      throw new Error(body.error ?? `HTTP ${response.status}`);
    }
    return body as { ok: true; status: 'consumed'; targetId: string };
  } finally {
    encoded.fill(0);
    window.clearTimeout(timeout);
  }
}

// ── API client ────────────────────────────────────────────────────────────────

export const adminApiClient = {

  ping() {
    return req<AdminUser & { ok: true; authMode: string }>('/api/admin/ping');
  },

  getEnterprisePlatformOverview() {
    return req<EnterprisePlatformOverview>('/api/admin/platform/v1/overview');
  },

  getEnterprisePlatformEvidence(limit = 30) {
    const bounded = Math.max(1, Math.min(Math.trunc(limit), 100));
    return req<{ ok: true; evidence: EnterpriseEvidenceReceipt[]; count: number }>(
      `/api/admin/platform/v1/evidence?limit=${bounded}`,
    );
  },

  runEnterprisePlatformCanary(
    scope: 'readiness' | 'completion',
    modelId?: string,
  ) {
    return req<EnterpriseCanaryResult>('/api/admin/platform/v1/canaries', {
      method: 'POST',
      body: JSON.stringify({
        scope,
        ...(modelId ? { modelId } : {}),
        confirmed: scope === 'completion',
      }),
    }, scope === 'completion' ? 120_000 : 30_000);
  },

  getEnterprisePlatformOpenApi() {
    return req<Record<string, unknown>>('/api/admin/platform/v1/openapi.json');
  },

  getUsers(p?: { page?: number; search?: string; limit?: number }) {
    const q = new URLSearchParams();
    if (p?.page)   q.set('page',   String(p.page));
    if (p?.search) q.set('search', p.search);
    if (p?.limit)  q.set('limit',  String(p.limit));
    return req<{ users: AdminUser[]; total: number; page: number }>(`/api/admin/users?${q}`);
  },

  updateUser(id: string, changes: Partial<Pick<AdminUser, 'role' | 'credits' | 'subscriptionStatus' | 'isBanned'>>) {
    return req<{ ok: boolean; user: AdminUser }>(`/api/admin/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    });
  },

  adjustCredits(
    id: string,
    amount: number,
    reason: string,
    idempotencyKey = crypto.randomUUID(),
  ) {
    return req<{
      ok: true;
      newBalance: number;
      duplicate: boolean;
      idempotencyKey: string;
    }>(`/api/admin/users/${id}/credit-adjustment`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ amount, reason }),
    });
  },

  getTransactions(p?: { userId?: string; type?: string; page?: number; limit?: number }) {
    const q = new URLSearchParams();
    if (p?.userId) q.set('user_id', p.userId);
    if (p?.type)   q.set('type',    p.type);
    if (p?.page)   q.set('page',    String(p.page));
    if (p?.limit)  q.set('limit',   String(p.limit));
    return req<{ transactions: Transaction[]; total: number; page: number }>(`/api/admin/transactions?${q}`);
  },

  getBillingStats() {
    return req<BillingStats>('/api/admin/billing/stats');
  },

  getLauncherTools() {
    return req<{ tools: LauncherToolOverride[] }>('/api/admin/launcher/tools');
  },

  updateLauncherTool(id: string, changes: Partial<Pick<LauncherToolOverride, 'disabled' | 'badge' | 'sortOrder'>>) {
    return req<{ ok: boolean }>(`/api/admin/launcher/tools/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    });
  },

  getLlmRoutes() {
    return req<{
      routes: LlmRoute[];
      billingCategories: LlmBillingCategoryOption[];
      revolverStats: LlmRevolverStats;
      revolverV3: LlmRevolverV3Status;
      manualCreditsPerUnitEditing: false;
    }>('/api/admin/llm/routes');
  },

  updateLlmRoute(id: string, changes: LlmRouteUpdate) {
    return req<{ ok: boolean; route: LlmRoute }>(`/api/admin/llm/routes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    });
  },

  resetLlmRouteRevolver(id: string) {
    return req<{ ok: true; routeId: string; quotaScope: string; status: 'ready' }>(
      `/api/admin/llm/routes/${id}/revolver-reset`,
      { method: 'POST', body: '{}' },
    );
  },

  getFreeRevolverProviders() {
    return req<{
      ok: true;
      truthOwner: string;
      keyStorage: string;
      activationRule: string;
      providers: FreeRevolverProviderSource[];
    }>('/api/admin/llm/revolver-v3/providers');
  },

  createFreeRevolverProvider(input: {
    label: string;
    apiBase: string;
    authMode: FreeRevolverProviderAuthMode;
  }) {
    return req<{
      ok: true;
      sourceId: string;
      ownerRequestId: string | null;
      ownerUrl: string | null;
      nextAction: string;
    }>('/api/admin/llm/revolver-v3/providers', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  renewFreeRevolverProviderKey(sourceId: string) {
    return req<{ ok: true; sourceId: string; ownerRequestId: string; ownerUrl: string }>(
      `/api/admin/llm/revolver-v3/providers/${encodeURIComponent(sourceId)}/owner-input`,
      { method: 'POST', body: '{}' },
    );
  },

  resolveFreeRevolverOwnerInput(requestId: string, protectedValue: string) {
    return resolveProtectedOwnerInput(requestId, protectedValue);
  },

  discoverFreeRevolverProvider(sourceId: string, maxAutoActivate = 20) {
    return req<{
      ok: boolean;
      status: FreeRevolverProviderStatus;
      sourceId: string;
      modelsUrl: string;
      discovered: number;
      freeVerified: number;
      activated: Array<{
        modelId: string;
        routeId?: string;
        alias?: string;
        canaryRequestId?: string;
        canaryCostState?: 'zero' | 'unreported';
      }>;
      blocked: Array<{ modelId: string; error?: string }>;
      unverified: string[];
      keyStoredBy: string;
    }>(`/api/admin/llm/revolver-v3/providers/${encodeURIComponent(sourceId)}/discover`, {
      method: 'POST',
      body: JSON.stringify({ maxAutoActivate }),
    }, 180_000);
  },

  recheckFreeRevolverProvider(sourceId: string) {
    return req<{
      ok: boolean;
      status: FreeRevolverProviderStatus;
      ready: string[];
      blocked: string[];
    }>(`/api/admin/llm/revolver-v3/providers/${encodeURIComponent(sourceId)}/recheck`, {
      method: 'POST',
      body: '{}',
    }, 180_000);
  },

  updateFreeRevolverProvider(sourceId: string, enabled: boolean) {
    return req<{ ok: true; sourceId: string; enabled: boolean }>(
      `/api/admin/llm/revolver-v3/providers/${encodeURIComponent(sourceId)}`,
      { method: 'PATCH', body: JSON.stringify({ enabled }) },
    );
  },

  getLlmModelCatalog() {
    return req<{
      models: LlmModelCatalogEntry[];
      billingCategories: LlmBillingCategoryOption[];
      pricingAuthority: string;
    }>('/api/admin/llm/model-catalog');
  },

  attachLlmModel(input: {
    modelId: string;
    displayName?: string;
    billingCategory: LlmBillingCategory;
    markupMultiplier: number;
    priority: number;
  }) {
    return req<{ ok: true; routeId: string; modelId: string }>(
      '/api/admin/llm/model-catalog/attach',
      { method: 'POST', body: JSON.stringify(input) },
      120_000,
    );
  },

  getAuditLog(p?: { page?: number; limit?: number }) {
    const q = new URLSearchParams();
    if (p?.page)  q.set('page',  String(p.page));
    if (p?.limit) q.set('limit', String(p.limit));
    return req<{ entries: AuditEntry[]; total: number; page: number }>(`/api/admin/audit-log?${q}`);
  },

  // ── Payment Methods ──────────────────────────────────────────────────────

  getPaymentMethods() {
    return req<{ paymentMethods: PaymentMethod[]; error?: string }>(
      '/api/admin/payment-methods',
    );
  },

  updatePaymentMethod(
    id: string,
    changes: { enabled?: boolean; label?: string; config?: Record<string, string> },
  ) {
    return req<{ ok: boolean }>(`/api/admin/payment-methods/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    });
  },

  initPaymentMethods() {
    return req<{ ok: boolean; inserted: number }>('/api/admin/payment-methods/init', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  // ── Credit Packages ──────────────────────────────────────────────────────

  getCreditPackages() {
    return req<{ packages: CreditPackage[]; error?: string }>(
      '/api/admin/credit-packages',
    );
  },

  initCreditPackages() {
    return req<{ ok: boolean; inserted: number }>('/api/admin/credit-packages/init', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  updateCreditPackage(
    id: string,
    changes: Partial<Pick<CreditPackage, 'name' | 'credits' | 'priceEur' | 'description' | 'enabled' | 'sortOrder'>>,
  ) {
    return req<{ ok: boolean }>(`/api/admin/credit-packages/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    });
  },

  deleteCreditPackage(id: string) {
    return req<{ ok: boolean }>(`/api/admin/credit-packages/${id}`, {
      method: 'DELETE',
    });
  },

  // ── Crypto confirmation (admin only) ─────────────────────────────────────

  confirmCryptoPayment(userId: string, packageId: string, txHash: string) {
    return req<{ ok: boolean; creditsAdded: number; newBalance: number }>(
      '/api/admin/payment-methods/crypto/confirm',
      {
        method: 'POST',
        body: JSON.stringify({ userId, packageId, txHash }),
      },
    );
  },

  // ── Toolchain (universal) ────────────────────────────────────────────────

  toolchainManifest() {
    return req<{
      name: string;
      tools: Array<{
        name: string;
        description: string;
        write_action: boolean;
        requires_confirm?: boolean;
        input_schema: unknown;
      }>;
    }>('/api/toolchain/universal/manifest');
  },

  toolchainStatus() {
    return req<{
      ok: boolean;
      name: string;
      proxy_via: string;
    }>('/api/toolchain/universal/status');
  },

  toolchainBriefing() {
    return req<{
      name: string;
      interfaces: string[];
      default_write_policy: unknown;
      project_profile: unknown;
    }>('/api/toolchain/universal/briefing');
  },

  // ── Toolchain Tools (Admin) ──────────────────────────────────────────────

  getToolchainTools() {
    return req<{
      tools: Array<{
        id: string;
        name: string;
        description: string;
        inputSchema: unknown;
        enabled: boolean;
        writeAction: boolean;
        requiresConfirm: boolean;
        sortOrder: number;
      }>;
    }>('/api/admin/toolchain/tools');
  },

  createToolchainTool(data: {
    name: string;
    description?: string;
    inputSchema?: unknown;
    enabled?: boolean;
    writeAction?: boolean;
    requiresConfirm?: boolean;
    sortOrder?: number;
  }) {
    return req<{ ok: boolean; id: string }>('/api/admin/toolchain/tools', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateToolchainTool(id: string, changes: Partial<{
    name: string;
    description: string;
    inputSchema: unknown;
    enabled: boolean;
    writeAction: boolean;
    requiresConfirm: boolean;
    sortOrder: number;
  }>) {
    return req<{ ok: boolean }>(`/api/admin/toolchain/tools/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    });
  },

  deleteToolchainTool(id: string) {
    return req<{ ok: boolean }>(`/api/admin/toolchain/tools/${id}`, {
      method: 'DELETE',
    });
  },
} as const;
