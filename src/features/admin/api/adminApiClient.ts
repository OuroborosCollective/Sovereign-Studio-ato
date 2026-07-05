/**
 * adminApiClient — Real HTTP client for sovereign-backend admin API.
 *
 * Base URL resolved from VITE_ADMIN_API_BASE env var (set in CI and .env).
 * Auth: Authorization: Bearer <admin-api-key> stored in localStorage.
 * Flask returns camelCase via SQL AS-aliases — all types here are camelCase.
 *
 * Issue #460
 */

// Resolved at build time by Vite; falls back to production URL.
export const ADMIN_API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

export const ADMIN_KEY_STORAGE = 'sovereign_admin_api_key';

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

export interface LlmRoute {
  id: string;
  modelId: string;
  modelName: string;
  provider: string;
  creditsPerUnit: number;
  disabled: boolean;
  priority: number;
}

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

// ── Key management ────────────────────────────────────────────────────────────

export function getAdminKey(): string {
  return localStorage.getItem(ADMIN_KEY_STORAGE) ?? '';
}
export function setAdminKey(key: string): void {
  localStorage.setItem(ADMIN_KEY_STORAGE, key.trim());
}
export function clearAdminKey(): void {
  localStorage.removeItem(ADMIN_KEY_STORAGE);
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  const key = getAdminKey();
  if (!key) throw new Error('Admin-API-Key fehlt. Bitte im Panel eintragen.');

  const res = await fetch(`${ADMIN_API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${key}`,
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { error?: string };
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── API client ────────────────────────────────────────────────────────────────

export const adminApiClient = {

  ping() {
    return req<{ ok: boolean; role: string }>('/api/admin/ping');
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

  adjustCredits(id: string, amount: number, reason: string) {
    return req<{ ok: boolean }>(`/api/admin/users/${id}/credit-adjustment`, {
      method: 'POST',
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
    return req<{ routes: LlmRoute[] }>('/api/admin/llm/routes');
  },

  updateLlmRoute(id: string, changes: Partial<Pick<LlmRoute, 'creditsPerUnit' | 'disabled' | 'priority'>>) {
    return req<{ ok: boolean }>(`/api/admin/llm/routes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    });
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
} as const;
