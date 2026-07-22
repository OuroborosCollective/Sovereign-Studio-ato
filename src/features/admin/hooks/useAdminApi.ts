/**
 * useAdminApi — React hooks for the real sovereign-backend admin API.
 * Issue #460
 */

import { useState, useCallback, useEffect } from 'react';
import {
  adminApiClient,
  type AdminUser,
  type Transaction,
  type BillingStats,
  type LauncherToolOverride,
  type LlmRoute,
  type LlmRouteUpdate,
  type LlmBillingCategory,
  type LlmBillingCategoryOption,
  type LlmModelCatalogEntry,
  type LlmRevolverStats,
  type LlmRevolverV3Status,
  type FreeRevolverProviderSource,
  type FreeRevolverProviderAuthMode,
  type AuditEntry,
  type PaymentMethod,
} from '../api/adminApiClient';

// ── useAdminUsers ─────────────────────────────────────────────────────────────

export interface UseAdminUsersResult {
  users: AdminUser[];
  total: number;
  page: number;
  loading: boolean;
  error: string | null;
  search: string;
  setSearch: (s: string) => void;
  setPage: (p: number) => void;
  reload: () => void;
  updateUser: (id: string, changes: Partial<Pick<AdminUser, 'role' | 'credits' | 'subscriptionStatus' | 'isBanned'>>) => Promise<void>;
  adjustCredits: (id: string, amount: number, reason: string) => Promise<void>;
}

export function useAdminUsers(): UseAdminUsersResult {
  const [users, setUsers]   = useState<AdminUser[]>([]);
  const [total, setTotal]   = useState(0);
  const [page, setPage]     = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState<string | null>(null);
  const [tick, setTick]     = useState(0);

  const reload = useCallback(() => setTick(t => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null);
    adminApiClient.getUsers({ page, search, limit: 50 })
      .then(r => { if (!cancelled) { setUsers(r.users); setTotal(r.total); } })
      .catch(e => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [page, search, tick]);

  const updateUser = useCallback(async (id: string, changes: Partial<Pick<AdminUser, 'role' | 'credits' | 'subscriptionStatus' | 'isBanned'>>) => {
    await adminApiClient.updateUser(id, changes);
    reload();
  }, [reload]);

  const adjustCredits = useCallback(async (id: string, amount: number, reason: string) => {
    await adminApiClient.adjustCredits(id, amount, reason);
    reload();
  }, [reload]);

  return { users, total, page, loading, error, search, setSearch, setPage, reload, updateUser, adjustCredits };
}

// ── useAdminTransactions ──────────────────────────────────────────────────────

export interface UseAdminTransactionsResult {
  transactions: Transaction[];
  total: number;
  page: number;
  loading: boolean;
  error: string | null;
  filterUserId: string;
  filterType: string;
  setFilterUserId: (id: string) => void;
  setFilterType: (t: string) => void;
  setPage: (p: number) => void;
}

export function useAdminTransactions(): UseAdminTransactionsResult {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage]   = useState(1);
  const [filterUserId, setFilterUserId] = useState('');
  const [filterType,   setFilterType]   = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null);
    adminApiClient.getTransactions({ userId: filterUserId || undefined, type: filterType || undefined, page, limit: 50 })
      .then(r => { if (!cancelled) { setTransactions(r.transactions); setTotal(r.total); } })
      .catch(e => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [page, filterUserId, filterType]);

  return { transactions, total, page, loading, error, filterUserId, filterType, setFilterUserId, setFilterType, setPage };
}

// ── useAdminBillingStats ──────────────────────────────────────────────────────

export interface UseAdminBillingStatsResult {
  stats: BillingStats | null;
  loading: boolean;
  error: string | null;
}

export function useAdminBillingStats(): UseAdminBillingStatsResult {
  const [stats, setStats] = useState<BillingStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    adminApiClient.getBillingStats()
      .then(s => { if (!cancelled) setStats(s); })
      .catch(e => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { stats, loading, error };
}

// ── useAdminLauncherTools ─────────────────────────────────────────────────────

export interface UseAdminLauncherToolsResult {
  tools: LauncherToolOverride[];
  loading: boolean;
  error: string | null;
  updateTool: (id: string, changes: Partial<Pick<LauncherToolOverride, 'disabled' | 'badge' | 'sortOrder'>>) => Promise<void>;
}

export function useAdminLauncherTools(): UseAdminLauncherToolsResult {
  const [tools, setTools] = useState<LauncherToolOverride[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    adminApiClient.getLauncherTools()
      .then(r => { if (!cancelled) setTools(r.tools); })
      .catch(e => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tick]);

  const updateTool = useCallback(async (id: string, changes: Partial<Pick<LauncherToolOverride, 'disabled' | 'badge' | 'sortOrder'>>) => {
    await adminApiClient.updateLauncherTool(id, changes);
    setTick(t => t + 1);
  }, []);

  return { tools, loading, error, updateTool };
}

// ── useAdminLlmRoutes ─────────────────────────────────────────────────────────

export interface UseAdminLlmRoutesResult {
  routes: LlmRoute[];
  billingCategories: LlmBillingCategoryOption[];
  revolverStats: LlmRevolverStats | null;
  revolverV3: LlmRevolverV3Status | null;
  legacyDirectRouteCount: number;
  catalog: LlmModelCatalogEntry[];
  catalogError: string | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  updateRoute: (id: string, changes: LlmRouteUpdate) => Promise<void>;
  resetRevolver: (id: string) => Promise<void>;
  attachModel: (
    modelId: string,
    billingCategory: LlmBillingCategory,
    markupMultiplier: number,
    priority: number,
  ) => Promise<void>;
}

export function useAdminLlmRoutes(): UseAdminLlmRoutesResult {
  const [routes, setRoutes] = useState<LlmRoute[]>([]);
  const [billingCategories, setBillingCategories] = useState<LlmBillingCategoryOption[]>([]);
  const [revolverStats, setRevolverStats] = useState<LlmRevolverStats | null>(null);
  const [revolverV3, setRevolverV3] = useState<LlmRevolverV3Status | null>(null);
  const [legacyDirectRouteCount, setLegacyDirectRouteCount] = useState(0);
  const [catalog, setCatalog] = useState<LlmModelCatalogEntry[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);
  const reload = useCallback(() => setTick(value => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setCatalogError(null);
    Promise.allSettled([
      adminApiClient.getLlmRoutes(),
      adminApiClient.getLlmModelCatalog(),
    ]).then(([routesResult, catalogResult]) => {
      if (cancelled) return;
      if (routesResult.status === 'fulfilled') {
        setRoutes(routesResult.value.routes);
        setBillingCategories(routesResult.value.billingCategories);
        setRevolverStats(routesResult.value.revolverStats);
        setRevolverV3(routesResult.value.revolverV3);
        setLegacyDirectRouteCount(routesResult.value.legacyDirectRouteCount ?? 0);
      } else {
        setError(String(routesResult.reason));
      }
      if (catalogResult.status === 'fulfilled') {
        setCatalog(catalogResult.value.models);
      } else {
        setCatalog([]);
        setCatalogError(String(catalogResult.reason));
      }
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [tick]);

  const updateRoute = useCallback(async (id: string, changes: LlmRouteUpdate) => {
    await adminApiClient.updateLlmRoute(id, changes);
    reload();
  }, [reload]);

  const resetRevolver = useCallback(async (id: string) => {
    await adminApiClient.resetLlmRouteRevolver(id);
    reload();
  }, [reload]);

  const attachModel = useCallback(async (
    modelId: string,
    billingCategory: LlmBillingCategory,
    markupMultiplier: number,
    priority: number,
  ) => {
    await adminApiClient.attachLlmModel({
      modelId,
      billingCategory,
      markupMultiplier,
      priority,
    });
    reload();
  }, [reload]);

  return {
    routes,
    billingCategories,
    revolverStats,
    revolverV3,
    legacyDirectRouteCount,
    catalog,
    catalogError,
    loading,
    error,
    reload,
    updateRoute,
    resetRevolver,
    attachModel,
  };
}

// ── useAdminFreeRevolverProviders ────────────────────────────────────────────

export interface UseAdminFreeRevolverProvidersResult {
  providers: FreeRevolverProviderSource[];
  loading: boolean;
  error: string | null;
  reload: () => void;
  createAndDiscover: (input: {
    label: string;
    apiBase: string;
    authMode: FreeRevolverProviderAuthMode;
    apiKey: string;
  }) => Promise<void>;
  renewAndDiscover: (sourceId: string, apiKey: string) => Promise<void>;
  discover: (sourceId: string) => Promise<void>;
  recheck: (sourceId: string) => Promise<void>;
  toggle: (sourceId: string, enabled: boolean) => Promise<void>;
}

export function useAdminFreeRevolverProviders(): UseAdminFreeRevolverProvidersResult {
  const [providers, setProviders] = useState<FreeRevolverProviderSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick(value => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminApiClient.getFreeRevolverProviders()
      .then(result => { if (!cancelled) setProviders(result.providers); })
      .catch(reason => { if (!cancelled) setError(String(reason)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tick]);

  const createAndDiscover = useCallback(async (input: {
    label: string;
    apiBase: string;
    authMode: FreeRevolverProviderAuthMode;
    apiKey: string;
  }) => {
    setError(null);
    const created = await adminApiClient.createFreeRevolverProvider({
      label: input.label,
      apiBase: input.apiBase,
      authMode: input.authMode,
    });
    if (input.authMode === 'bearer' || input.authMode === 'x-api-key') {
      if (!created.ownerRequestId || input.apiKey.length < 8) {
        throw new Error('Ein gültiger API-Key ist für diesen Auth-Modus erforderlich.');
      }
      await adminApiClient.resolveFreeRevolverOwnerInput(created.ownerRequestId, input.apiKey);
    }
    await adminApiClient.discoverFreeRevolverProvider(created.sourceId);
    reload();
  }, [reload]);

  const renewAndDiscover = useCallback(async (sourceId: string, apiKey: string) => {
    setError(null);
    if (apiKey.length < 8) throw new Error('Der API-Key muss mindestens 8 Zeichen enthalten.');
    const ownerInput = await adminApiClient.renewFreeRevolverProviderKey(sourceId);
    await adminApiClient.resolveFreeRevolverOwnerInput(ownerInput.ownerRequestId, apiKey);
    await adminApiClient.discoverFreeRevolverProvider(sourceId);
    reload();
  }, [reload]);

  const discover = useCallback(async (sourceId: string) => {
    setError(null);
    await adminApiClient.discoverFreeRevolverProvider(sourceId);
    reload();
  }, [reload]);

  const recheck = useCallback(async (sourceId: string) => {
    setError(null);
    await adminApiClient.recheckFreeRevolverProvider(sourceId);
    reload();
  }, [reload]);

  const toggle = useCallback(async (sourceId: string, enabled: boolean) => {
    setError(null);
    await adminApiClient.updateFreeRevolverProvider(sourceId, enabled);
    reload();
  }, [reload]);

  return {
    providers,
    loading,
    error,
    reload,
    createAndDiscover,
    renewAndDiscover,
    discover,
    recheck,
    toggle,
  };
}

// ── useAdminPaymentMethods ────────────────────────────────────────────────────

export interface UseAdminPaymentMethodsResult {
  methods: PaymentMethod[];
  legacyIgnoredCount: number;
  loading: boolean;
  error: string | null;
  reload: () => void;
  toggleMethod: (id: string, enabled: boolean) => Promise<void>;
  saveConfig: (id: string, config: Record<string, string>) => Promise<void>;
  initDefaults: () => Promise<void>;
}

export function useAdminPaymentMethods(): UseAdminPaymentMethodsResult {
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [legacyIgnoredCount, setLegacyIgnoredCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);
  const reload = useCallback(() => setTick(t => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    adminApiClient.getPaymentMethods()
      .then(r => {
        if (!cancelled) {
          setMethods(r.paymentMethods);
          setLegacyIgnoredCount(r.legacyIgnoredCount ?? 0);
        }
      })
      .catch(e => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tick]);

  const toggleMethod = useCallback(async (id: string, enabled: boolean) => {
    await adminApiClient.updatePaymentMethod(id, { enabled });
    reload();
  }, [reload]);

  const saveConfig = useCallback(async (id: string, config: Record<string, string>) => {
    await adminApiClient.updatePaymentMethod(id, { config });
    reload();
  }, [reload]);

  const initDefaults = useCallback(async () => {
    await adminApiClient.initPaymentMethods();
    reload();
  }, [reload]);

  return {
    methods,
    legacyIgnoredCount,
    loading,
    error,
    reload,
    toggleMethod,
    saveConfig,
    initDefaults,
  };
}


// ── useAdminAuditLog ──────────────────────────────────────────────────────────

export interface UseAdminAuditLogResult {
  entries: AuditEntry[];
  total: number;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useAdminAuditLog(): UseAdminAuditLogResult {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);
  const reload = useCallback(() => setTick(t => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    adminApiClient.getAuditLog({ page: 1, limit: 100 })
      .then(r => { if (!cancelled) { setEntries(r.entries); setTotal(r.total); } })
      .catch(e => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tick]);

  return { entries, total, loading, error, reload };
}
