/**
 * LLM Route Budget Runtime Tests — Issue #446
 */

import { describe, it, expect } from 'vitest';
import {
  createRouteRegistry,
  getRouteById,
  createUserPlanState,
  isRouteAllowedForPlan,
  createBudgetLedger,
  recordRouteUsage,
  getRouteUsed,
  getBudgetForRoute,
  isRouteExhausted,
  remainingBudget,
  selectLlmRoute,
  toLlmBudgetInspectorSignal,
  summarizeLlmBudgetState,
  type LlmRoute,
  type LlmRouteRegistry,
  type LlmUserPlanState,
  type LlmBudgetLedger,
} from './llmRouteBudgetRuntime';

// ─────────────────────────────────────────────────────────────
// Fixtures
// ─────────────────────────────────────────────────────────────

const routeFast: LlmRoute = {
  id: 'fast',
  label: 'Fast Model',
  budgetByPlan: { free: 10, pro: 100, enterprise: Infinity },
  priority: 1,
};

const routeSmart: LlmRoute = {
  id: 'smart',
  label: 'Smart Model',
  budgetByPlan: { free: 3, pro: 50, enterprise: Infinity },
  priority: 2,
};

const routePremium: LlmRoute = {
  id: 'premium',
  label: 'Premium Model',
  budgetByPlan: { pro: 20, enterprise: Infinity },
  priority: 3,
};

function makeRegistry(routes: LlmRoute[] = [routeFast, routeSmart]): LlmRouteRegistry {
  return createRouteRegistry(routes);
}

function makePlan(planId: string, allowedRouteIds: string[]): LlmUserPlanState {
  return createUserPlanState(planId, allowedRouteIds);
}

// ─────────────────────────────────────────────────────────────
// Route Registry
// ─────────────────────────────────────────────────────────────

describe('createRouteRegistry', () => {
  it('stores routes sorted by priority', () => {
    const registry = createRouteRegistry([routeSmart, routeFast]);
    expect(registry.routes[0].id).toBe('fast');
    expect(registry.routes[1].id).toBe('smart');
  });

  it('accepts a single route', () => {
    const registry = createRouteRegistry([routeFast]);
    expect(registry.routes).toHaveLength(1);
  });

  it('accepts an empty list', () => {
    const registry = createRouteRegistry([]);
    expect(registry.routes).toHaveLength(0);
  });
});

describe('getRouteById', () => {
  it('returns the matching route', () => {
    const registry = makeRegistry();
    expect(getRouteById(registry, 'fast')?.id).toBe('fast');
  });

  it('returns null when route is not found', () => {
    const registry = makeRegistry();
    expect(getRouteById(registry, 'unknown')).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────
// User Plan State
// ─────────────────────────────────────────────────────────────

describe('createUserPlanState', () => {
  it('stores plan id and allowed route ids', () => {
    const plan = createUserPlanState('free', ['fast']);
    expect(plan.planId).toBe('free');
    expect(plan.allowedRouteIds).toEqual(['fast']);
  });
});

describe('isRouteAllowedForPlan', () => {
  it('returns true when route is in allowed list', () => {
    const plan = makePlan('free', ['fast', 'smart']);
    expect(isRouteAllowedForPlan(plan, 'fast')).toBe(true);
  });

  it('returns false when route is not in allowed list', () => {
    const plan = makePlan('free', ['fast']);
    expect(isRouteAllowedForPlan(plan, 'premium')).toBe(false);
  });

  it('returns false when allowed list is empty', () => {
    const plan = makePlan('free', []);
    expect(isRouteAllowedForPlan(plan, 'fast')).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────
// Budget Ledger
// ─────────────────────────────────────────────────────────────

describe('createBudgetLedger', () => {
  it('starts with no entries', () => {
    const ledger = createBudgetLedger();
    expect(ledger.entries).toEqual({});
  });
});

describe('recordRouteUsage', () => {
  it('creates a new entry on first usage', () => {
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast');
    expect(getRouteUsed(ledger, 'fast')).toBe(1);
  });

  it('accumulates usage across calls', () => {
    let ledger = createBudgetLedger();
    ledger = recordRouteUsage(ledger, 'fast');
    ledger = recordRouteUsage(ledger, 'fast');
    ledger = recordRouteUsage(ledger, 'fast', 3);
    expect(getRouteUsed(ledger, 'fast')).toBe(5);
  });

  it('tracks multiple routes independently', () => {
    let ledger = createBudgetLedger();
    ledger = recordRouteUsage(ledger, 'fast', 4);
    ledger = recordRouteUsage(ledger, 'smart', 2);
    expect(getRouteUsed(ledger, 'fast')).toBe(4);
    expect(getRouteUsed(ledger, 'smart')).toBe(2);
  });

  it('does not mutate the original ledger', () => {
    const original = createBudgetLedger();
    recordRouteUsage(original, 'fast');
    expect(getRouteUsed(original, 'fast')).toBe(0);
  });
});

describe('getRouteUsed', () => {
  it('returns 0 for unknown route', () => {
    expect(getRouteUsed(createBudgetLedger(), 'nonexistent')).toBe(0);
  });
});

describe('getBudgetForRoute', () => {
  it('returns the budget for the given plan', () => {
    expect(getBudgetForRoute(routeFast, 'free')).toBe(10);
    expect(getBudgetForRoute(routeFast, 'pro')).toBe(100);
  });

  it('returns 0 when plan has no budget entry for this route', () => {
    expect(getBudgetForRoute(routePremium, 'free')).toBe(0);
  });

  it('returns Infinity for unlimited plans', () => {
    expect(getBudgetForRoute(routeFast, 'enterprise')).toBe(Infinity);
  });
});

describe('isRouteExhausted', () => {
  it('returns false when usage is below budget', () => {
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 5);
    expect(isRouteExhausted(routeFast, ledger, 'free')).toBe(false);
  });

  it('returns true when usage equals budget', () => {
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 10);
    expect(isRouteExhausted(routeFast, ledger, 'free')).toBe(true);
  });

  it('returns true when usage exceeds budget', () => {
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 15);
    expect(isRouteExhausted(routeFast, ledger, 'free')).toBe(true);
  });

  it('returns false for unlimited budget (Infinity)', () => {
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 9999);
    expect(isRouteExhausted(routeFast, ledger, 'enterprise')).toBe(false);
  });

  it('returns true when route has zero budget for plan', () => {
    const ledger = createBudgetLedger();
    expect(isRouteExhausted(routePremium, ledger, 'free')).toBe(true);
  });
});

describe('remainingBudget', () => {
  it('returns full budget when nothing is used', () => {
    expect(remainingBudget(routeFast, createBudgetLedger(), 'free')).toBe(10);
  });

  it('returns reduced budget after usage', () => {
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 7);
    expect(remainingBudget(routeFast, ledger, 'free')).toBe(3);
  });

  it('returns 0 when exhausted (not negative)', () => {
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 15);
    expect(remainingBudget(routeFast, ledger, 'free')).toBe(0);
  });

  it('returns Infinity for unlimited plans', () => {
    expect(remainingBudget(routeFast, createBudgetLedger(), 'enterprise')).toBe(Infinity);
  });
});

// ─────────────────────────────────────────────────────────────
// Route Selection
// ─────────────────────────────────────────────────────────────

describe('selectLlmRoute', () => {
  describe('available — primary route has budget', () => {
    it('selects the highest-priority allowed route', () => {
      const registry = makeRegistry([routeFast, routeSmart]);
      const plan = makePlan('free', ['fast', 'smart']);
      const ledger = createBudgetLedger();

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('available');
      expect(result.selectedRoute?.id).toBe('fast');
      expect(result.exhaustedRouteIds).toHaveLength(0);
    });

    it('does not mark any routes as exhausted when primary is available', () => {
      const registry = makeRegistry([routeFast, routeSmart]);
      const plan = makePlan('pro', ['fast', 'smart']);
      const ledger = recordRouteUsage(createBudgetLedger(), 'smart', 10);

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('available');
      expect(result.selectedRoute?.id).toBe('fast');
    });
  });

  describe('fallback — primary exhausted, fallback available', () => {
    it('falls back to next allowed route when primary is exhausted', () => {
      const registry = makeRegistry([routeFast, routeSmart]);
      const plan = makePlan('free', ['fast', 'smart']);
      const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 10);

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('fallback');
      expect(result.selectedRoute?.id).toBe('smart');
      expect(result.exhaustedRouteIds).toContain('fast');
    });

    it('includes all exhausted routes in exhaustedRouteIds', () => {
      const registry = makeRegistry([routeFast, routeSmart, routePremium]);
      const plan = makePlan('pro', ['fast', 'smart', 'premium']);
      let ledger = createBudgetLedger();
      ledger = recordRouteUsage(ledger, 'fast', 100);
      ledger = recordRouteUsage(ledger, 'smart', 50);

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('fallback');
      expect(result.selectedRoute?.id).toBe('premium');
      expect(result.exhaustedRouteIds).toContain('fast');
      expect(result.exhaustedRouteIds).toContain('smart');
    });

    it('skips routes with zero budget for the plan', () => {
      const registry = makeRegistry([routePremium, routeSmart]);
      const plan = makePlan('free', ['premium', 'smart']);
      const ledger = createBudgetLedger();

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('fallback');
      expect(result.selectedRoute?.id).toBe('smart');
      expect(result.exhaustedRouteIds).toContain('premium');
    });
  });

  describe('blocked — all allowed routes exhausted', () => {
    it('returns blocked when all routes are exhausted', () => {
      const registry = makeRegistry([routeFast, routeSmart]);
      const plan = makePlan('free', ['fast', 'smart']);
      let ledger = createBudgetLedger();
      ledger = recordRouteUsage(ledger, 'fast', 10);
      ledger = recordRouteUsage(ledger, 'smart', 3);

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('blocked');
      expect(result.selectedRoute).toBeNull();
      expect(result.exhaustedRouteIds).toContain('fast');
      expect(result.exhaustedRouteIds).toContain('smart');
    });

    it('returns blocked when plan has no allowed routes', () => {
      const registry = makeRegistry([routeFast]);
      const plan = makePlan('free', []);
      const ledger = createBudgetLedger();

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('blocked');
      expect(result.selectedRoute).toBeNull();
      expect(result.reason).toMatch(/No routes allowed/i);
    });

    it('returns blocked when all plan routes have zero budget', () => {
      const registry = makeRegistry([routePremium]);
      const plan = makePlan('free', ['premium']);
      const ledger = createBudgetLedger();

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('blocked');
      expect(result.selectedRoute).toBeNull();
    });

    it('returns blocked when allowed routes are not in registry', () => {
      const registry = makeRegistry([routeFast]);
      const plan = makePlan('free', ['unknown-route']);
      const ledger = createBudgetLedger();

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('blocked');
      expect(result.selectedRoute).toBeNull();
    });
  });

  describe('unlimited budget routes', () => {
    it('never exhausts an unlimited route', () => {
      const registry = makeRegistry([routeFast]);
      const plan = makePlan('enterprise', ['fast']);
      const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 999999);

      const result = selectLlmRoute(registry, plan, ledger);

      expect(result.status).toBe('available');
      expect(result.selectedRoute?.id).toBe('fast');
    });
  });
});

// ─────────────────────────────────────────────────────────────
// Inspector Signal
// ─────────────────────────────────────────────────────────────

describe('toLlmBudgetInspectorSignal', () => {
  const plan = makePlan('free', ['fast']);

  it('produces a green signal when route is available', () => {
    const result = selectLlmRoute(makeRegistry([routeFast]), plan, createBudgetLedger());
    const signal = toLlmBudgetInspectorSignal(result, plan);

    expect(signal.lamp).toBe('green');
    expect(signal.id).toBe('llm-route-budget');
    expect(signal.targetTab).toBe('runtime');
    expect(signal.visible).toBe(true);
    expect(signal.source).toContain('free');
  });

  it('produces a yellow signal when route is in fallback', () => {
    let ledger = recordRouteUsage(createBudgetLedger(), 'fast', 10);
    const result = selectLlmRoute(makeRegistry([routeFast, routeSmart]), makePlan('free', ['fast', 'smart']), ledger);
    const signal = toLlmBudgetInspectorSignal(result, makePlan('free', ['fast', 'smart']));

    expect(signal.lamp).toBe('yellow');
  });

  it('produces a red signal when blocked', () => {
    let ledger = recordRouteUsage(createBudgetLedger(), 'fast', 10);
    const result = selectLlmRoute(makeRegistry([routeFast]), plan, ledger);
    const signal = toLlmBudgetInspectorSignal(result, plan);

    expect(signal.lamp).toBe('red');
    expect(signal.message).toContain('Blockiert');
  });

  it('includes updatedAt as a finite number', () => {
    const result = selectLlmRoute(makeRegistry([routeFast]), plan, createBudgetLedger());
    const signal = toLlmBudgetInspectorSignal(result, plan);

    expect(typeof signal.updatedAt).toBe('number');
    expect(Number.isFinite(signal.updatedAt)).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────
// Summary
// ─────────────────────────────────────────────────────────────

describe('summarizeLlmBudgetState', () => {
  it('summarizes used and total budget for each allowed route', () => {
    const registry = makeRegistry([routeFast, routeSmart]);
    const plan = makePlan('free', ['fast', 'smart']);
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 4);

    const summary = summarizeLlmBudgetState(registry, plan, ledger);

    expect(summary).toContain('4/10');
    expect(summary).toContain('0/3');
  });

  it('shows "unlimited" for Infinity budget', () => {
    const registry = makeRegistry([routeFast]);
    const plan = makePlan('enterprise', ['fast']);
    const ledger = recordRouteUsage(createBudgetLedger(), 'fast', 500);

    const summary = summarizeLlmBudgetState(registry, plan, ledger);

    expect(summary).toContain('unlimited');
    expect(summary).toContain('500');
  });

  it('returns no-routes message when plan has no allowed routes', () => {
    const registry = makeRegistry([routeFast]);
    const plan = makePlan('free', []);
    const ledger = createBudgetLedger();

    const summary = summarizeLlmBudgetState(registry, plan, ledger);

    expect(summary).toMatch(/No routes available/i);
  });
});
