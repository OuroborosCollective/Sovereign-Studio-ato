/**
 * adminApiClient — Real HTTP client for sovereign-backend admin API.
 *
 * Base URL : https://sovereign-backend.arelorian.de
 * Auth     : Authorization: Bearer <admin-api-key>
 *
 * The API key is entered once in AdminPanel and stored in localStorage.
 * Flask returns camelCase (via SQL AS-aliases), so all types here are camelCase.
 *
 * Issue #460
 */

export const ADMIN_API_BASE = 'https://sovereign-backend.arelorian.de';
export const ADMIN_KEY_STORAGE = 'sovereign_admin_api_key';

// ── Types ─────────────────────────────────────────────────────────────────────

export type UserRole = 'user' | 'admin' | 'superadmin';
export type SubscriptionStatus = 'active' | 'canceled' | 'past_due' | 'trialing' | 'free';

export interface AdminUser {
  id: string;
  email: string;
  displayName: string;          // SQL: display_name AS "displayName"
  role: UserRole;
  credits: number;
  subscriptionStatus: SubscriptionStatus; // SQL: subscription_status AS "subscriptionStatus"
  isBanned: boolean;            // SQL: is_banned AS "isBanned"
  createdAt: string;            // SQL: created_at AS "createdAt"
  lastActiveAt: string | null;  // SQL: last_active_at AS "lastActiveAt"
}

export interface Transaction {
  id: string;
  userId: string | null;        // SQL: user_id::text AS "userId"
  userEmail: string;            // SQL: user_email AS "userEmail"
  type: 'credit_purchase' | 'subscription' | 'refund' | 'adjustment' | 'usage';
  amount: number;
  currency: string;
  status: 'completed' | 'pending' | 'failed' | 'refunded';
  description: string;
  createdAt: string;            // SQL: created_at AS "createdAt"
}

export interface BillingStats {
  mrr: number;
  activeSubscriptions: number;  // Flask key: activeSubscriptions
  totalCredits: number;         // Flask key: totalCredits
  totalRevenue: number;
  churnRate: number;
}

export interface LauncherToolOverride {
  id: string;
  label: string;
  disabled: boolean;
  badge: 'NEU' | 'BETA' | 'PRO' | null;
  sortOrder: number;            // SQL: sort_order AS "sortOrder"
}

export interface LlmRoute {
  id: string;
  modelId: string;              // SQL: model_id AS "modelId"
  modelName: string;            // SQL: model_name AS "modelName"
  provider: string;
  creditsPerUnit: number;       // SQL: credits_per_unit AS "creditsPerUnit"
  disabled: boolean;
  priority: number;
}

export interface AuditEntry {
  id: string;
  adminId: string;              // SQL: admin_id AS "adminId"
  adminEmail: string;           // SQL: admin_email AS "adminEmail"
  action: string;
  targetId: string | null;      // SQL: target_id AS "targetId"
  changes: Record<string, unknown>;
  createdAt: string;            // SQL: created_at AS "createdAt"
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

  // Users
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
      body: JSON.stringify(changes), // Flask reads subscriptionStatus, isBanned
    });
  },

  adjustCredits(id: string, amount: number, reason: string) {
    return req<{ ok: boolean }>(`/api/admin/users/${id}/credit-adjustment`, {
      method: 'POST',
      body: JSON.stringify({ amount, reason }),
    });
  },

  // Transactions
  getTransactions(p?: { userId?: string; type?: string; page?: number; limit?: number }) {
    const q = new URLSearchParams();
    if (p?.userId) q.set('user_id', p.userId);
    if (p?.type)   q.set('type',    p.type);
    if (p?.page)   q.set('page',    String(p.page));
    if (p?.limit)  q.set('limit',   String(p.limit));
    return req<{ transactions: Transaction[]; total: number; page: number }>(`/api/admin/transactions?${q}`);
  },

  // Billing
  getBillingStats() {
    return req<BillingStats>('/api/admin/billing/stats');
  },

  // Launcher
  getLauncherTools() {
    return req<{ tools: LauncherToolOverride[] }>('/api/admin/launcher/tools');
  },

  updateLauncherTool(id: string, changes: Partial<Pick<LauncherToolOverride, 'disabled' | 'badge' | 'sortOrder'>>) {
    return req<{ ok: boolean }>(`/api/admin/launcher/tools/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes), // Flask reads sortOrder → sort_order
    });
  },

  // LLM
  getLlmRoutes() {
    return req<{ routes: LlmRoute[] }>('/api/admin/llm/routes');
  },

  updateLlmRoute(id: string, changes: Partial<Pick<LlmRoute, 'creditsPerUnit' | 'disabled' | 'priority'>>) {
    return req<{ ok: boolean }>(`/api/admin/llm/routes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes), // Flask reads creditsPerUnit → credits_per_unit
    });
  },

  // Audit
  getAuditLog(p?: { page?: number; limit?: number }) {
    const q = new URLSearchParams();
    if (p?.page)  q.set('page',  String(p.page));
    if (p?.limit) q.set('limit', String(p.limit));
    return req<{ entries: AuditEntry[]; total: number; page: number }>(`/api/admin/audit-log?${q}`);
  },
} as const;
