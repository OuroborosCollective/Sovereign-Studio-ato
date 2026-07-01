/**
 * LLM Route Budget Runtime — Issue #446
 *
 * Runtime contract for LLM route budgets and route fallback.
 * Tracks user plan state, a route registry, a budget ledger,
 * and selects or falls back across allowed routes.
 *
 * Rules:
 * - No fake truth: all state derives from real ledger entries.
 * - No percentages: report step counts and honest labels.
 * - No mocks in live paths.
 * - UI only displays this runtime state.
 */

import type { QuietInspectorSignal, QuietInspectorLamp } from './quietInspectorHintPolicy';

// ─────────────────────────────────────────────────────────────
// Route Registry
// ─────────────────────────────────────────────────────────────

/** A single registered LLM route with its label and per-plan budgets. */
export interface LlmRoute {
  readonly id: string;
  readonly label: string;
  /** Budget limit per plan tier. Use Infinity for unlimited. */
  readonly budgetByPlan: Readonly<Record<string, number>>;
  /** Priority order for fallback — lower number = tried first. */
  readonly priority: number;
}

export interface LlmRouteRegistry {
  readonly routes: readonly LlmRoute[];
}

export function createRouteRegistry(routes: readonly LlmRoute[]): LlmRouteRegistry {
  const sorted = [...routes].sort((a, b) => a.priority - b.priority);
  return { routes: sorted };
}

export function getRouteById(registry: LlmRouteRegistry, id: string): LlmRoute | null {
  return registry.routes.find((r) => r.id === id) ?? null;
}

// ─────────────────────────────────────────────────────────────
// User Plan State
// ─────────────────────────────────────────────────────────────

export interface LlmUserPlanState {
  readonly planId: string;
  /** Route IDs the current plan allows, in preference order. */
  readonly allowedRouteIds: readonly string[];
}

export function createUserPlanState(planId: string, allowedRouteIds: readonly string[]): LlmUserPlanState {
  return { planId, allowedRouteIds };
}

export function isRouteAllowedForPlan(plan: LlmUserPlanState, routeId: string): boolean {
  return plan.allowedRouteIds.includes(routeId);
}

// ─────────────────────────────────────────────────────────────
// Budget Ledger
// ─────────────────────────────────────────────────────────────

export interface LlmBudgetLedgerEntry {
  readonly routeId: string;
  readonly used: number;
}

export interface LlmBudgetLedger {
  readonly entries: Readonly<Record<string, LlmBudgetLedgerEntry>>;
}

export function createBudgetLedger(): LlmBudgetLedger {
  return { entries: {} };
}

export function recordRouteUsage(ledger: LlmBudgetLedger, routeId: string, count: number = 1): LlmBudgetLedger {
  const existing = ledger.entries[routeId];
  const used = (existing?.used ?? 0) + count;
  return {
    entries: {
      ...ledger.entries,
      [routeId]: { routeId, used },
    },
  };
}

export function getRouteUsed(ledger: LlmBudgetLedger, routeId: string): number {
  return ledger.entries[routeId]?.used ?? 0;
}

export function getBudgetForRoute(route: LlmRoute, planId: string): number {
  return route.budgetByPlan[planId] ?? 0;
}

export function isRouteExhausted(route: LlmRoute, ledger: LlmBudgetLedger, planId: string): boolean {
  const budget = getBudgetForRoute(route, planId);
  if (!Number.isFinite(budget)) return false;
  const used = getRouteUsed(ledger, route.id);
  return used >= budget;
}

export function remainingBudget(route: LlmRoute, ledger: LlmBudgetLedger, planId: string): number {
  const budget = getBudgetForRoute(route, planId);
  if (!Number.isFinite(budget)) return Infinity;
  const used = getRouteUsed(ledger, route.id);
  return Math.max(0, budget - used);
}

// ─────────────────────────────────────────────────────────────
// Route Selection
// ─────────────────────────────────────────────────────────────

export type LlmRouteSelectionStatus =
  | 'available'   // route selected and has budget
  | 'fallback'    // primary was exhausted, using a fallback route
  | 'blocked';    // all allowed routes are exhausted or unavailable

export interface LlmRouteSelectionResult {
  readonly status: LlmRouteSelectionStatus;
  readonly selectedRoute: LlmRoute | null;
  readonly reason: string;
  readonly exhaustedRouteIds: readonly string[];
}

/**
 * Select the best available route for the user's plan.
 * Iterates routes in the order defined by plan.allowedRouteIds (preference order).
 * Falls back to the next allowed route when the current one is exhausted.
 * Returns blocked status honestly when no route has budget.
 */
export function selectLlmRoute(
  registry: LlmRouteRegistry,
  plan: LlmUserPlanState,
  ledger: LlmBudgetLedger,
): LlmRouteSelectionResult {
  if (plan.allowedRouteIds.length === 0) {
    return {
      status: 'blocked',
      selectedRoute: null,
      reason: 'No routes allowed for this plan.',
      exhaustedRouteIds: [],
    };
  }

  // Resolve routes in the plan's preferred order (allowedRouteIds is preference-ordered).
  const orderedRoutes: LlmRoute[] = [];
  for (const id of plan.allowedRouteIds) {
    const route = getRouteById(registry, id);
    if (route) orderedRoutes.push(route);
  }

  if (orderedRoutes.length === 0) {
    return {
      status: 'blocked',
      selectedRoute: null,
      reason: 'No routes allowed for this plan.',
      exhaustedRouteIds: [],
    };
  }

  const exhaustedRouteIds: string[] = [];

  for (const route of orderedRoutes) {
    const budget = getBudgetForRoute(route, plan.planId);
    if (budget === 0 || isRouteExhausted(route, ledger, plan.planId)) {
      exhaustedRouteIds.push(route.id);
      continue;
    }

    if (exhaustedRouteIds.length === 0) {
      return {
        status: 'available',
        selectedRoute: route,
        reason: `Route "${route.label}" selected.`,
        exhaustedRouteIds: [],
      };
    }

    // Some routes before this one were exhausted — this is a fallback.
    return {
      status: 'fallback',
      selectedRoute: route,
      reason: `Fallback to "${route.label}" (${exhaustedRouteIds.length} route(s) exhausted).`,
      exhaustedRouteIds: [...exhaustedRouteIds],
    };
  }

  return {
    status: 'blocked',
    selectedRoute: null,
    reason: `All allowed routes exhausted (${exhaustedRouteIds.length} route(s) used up).`,
    exhaustedRouteIds: [...exhaustedRouteIds],
  };
}

// ─────────────────────────────────────────────────────────────
// Inspector Signal integration
// ─────────────────────────────────────────────────────────────

export function toLlmBudgetInspectorSignal(
  result: LlmRouteSelectionResult,
  plan: LlmUserPlanState,
): QuietInspectorSignal {
  let lamp: QuietInspectorLamp;
  if (result.status === 'available') lamp = 'green';
  else if (result.status === 'fallback') lamp = 'yellow';
  else lamp = 'red';

  const message = result.status === 'blocked'
    ? `LLM Budget: Blockiert — ${result.reason}`
    : `LLM Budget: ${result.selectedRoute?.label ?? '—'} — ${result.reason}`;

  return {
    id: 'llm-route-budget',
    source: `plan:${plan.planId}`,
    lamp,
    message,
    targetTab: 'runtime',
    visible: true,
    updatedAt: Date.now(),
  };
}

// ─────────────────────────────────────────────────────────────
// Summary helper
// ─────────────────────────────────────────────────────────────

export function summarizeLlmBudgetState(
  registry: LlmRouteRegistry,
  plan: LlmUserPlanState,
  ledger: LlmBudgetLedger,
): string {
  const parts: string[] = [];
  const allowedRoutes = registry.routes.filter((r) => isRouteAllowedForPlan(plan, r.id));

  for (const route of allowedRoutes) {
    const budget = getBudgetForRoute(route, plan.planId);
    const used = getRouteUsed(ledger, route.id);
    if (!Number.isFinite(budget)) {
      parts.push(`${route.label}: ${used} used (unlimited)`);
    } else {
      parts.push(`${route.label}: ${used}/${budget}`);
    }
  }

  if (parts.length === 0) return 'No routes available for this plan.';
  return parts.join(' · ');
}
