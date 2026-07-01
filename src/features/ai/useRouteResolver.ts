/**
 * useRouteResolver — Runtime route resolution for Sovereign Studio.
 *
 * Fetches the merged route config (defaults + admin DB overrides) from the
 * backend and caches results for 5 minutes.  Falls back to DEFAULT_ROUTES
 * when the backend is unreachable so the UI never silently breaks.
 *
 * Issue #461
 */

import type { UserApiKeys } from '../product/components/UserKeyManager';
import { DEFAULT_ROUTES, getDefaultRoute, type LlmRoute } from './routingConfig';

// ── 5-minute in-memory cache ──────────────────────────────────────────────────

interface CacheEntry {
  route: LlmRoute;
  expiresAt: number;
}

const CACHE_TTL_MS = 5 * 60 * 1000;
const _cache = new Map<string, CacheEntry>();

function cacheGet(routeId: string): LlmRoute | null {
  const entry = _cache.get(routeId);
  if (!entry || Date.now() > entry.expiresAt) return null;
  return entry.route;
}

function cacheSet(routeId: string, route: LlmRoute): void {
  _cache.set(routeId, { route, expiresAt: Date.now() + CACHE_TTL_MS });
}

/** Force-invalidate all cached routes (called after admin changes). */
export function invalidateRouteCache(): void {
  _cache.clear();
}

// ── Route resolution ──────────────────────────────────────────────────────────

/**
 * Resolves the active LlmRoute for the given routeId.
 *
 * Order of preference:
 * 1. In-memory cache (fresh)
 * 2. Backend GET /api/llm/routes/:id (merged defaults + admin overrides)
 * 3. Local DEFAULT_ROUTES fallback (when backend is unreachable)
 */
export async function resolveRoute(routeId: string): Promise<LlmRoute> {
  const cached = cacheGet(routeId);
  if (cached) return cached;

  try {
    const res = await fetch(`/api/llm/routes/${encodeURIComponent(routeId)}`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const route = (await res.json()) as LlmRoute;
    cacheSet(routeId, route);
    return route;
  } catch {
    const fallback = getDefaultRoute(routeId);
    if (fallback) return fallback;
    throw new Error(`Unbekannte Route: ${routeId}`);
  }
}

/**
 * Resolves all active routes (for display or pre-warming the cache).
 * Falls back to DEFAULT_ROUTES on network error.
 */
export async function resolveAllRoutes(): Promise<LlmRoute[]> {
  try {
    const res = await fetch('/api/llm/routes', { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as { routes: LlmRoute[] };
    for (const route of data.routes) cacheSet(route.id, route);
    return data.routes;
  } catch {
    return DEFAULT_ROUTES;
  }
}

/**
 * Returns true when the user has their own Gemini API key and the route
 * allows user-key override — in that case credit deduction is skipped.
 */
export function hasUserKeyOverride(routeId: string, userKeys: UserApiKeys): boolean {
  const route = cacheGet(routeId) ?? getDefaultRoute(routeId);
  if (!route?.userKeyOverride) return false;
  return !!(userKeys as Record<string, string | undefined>)['geminiKey'];
}
