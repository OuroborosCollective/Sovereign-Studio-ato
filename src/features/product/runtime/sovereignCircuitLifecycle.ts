export type SovereignCircuitPhase = 'closed' | 'open' | 'half-open';

export interface SovereignCircuitPolicy {
  failureThreshold: number;
  cooldownMs: number;
  halfOpenMaxAttempts: number;
}

export interface SovereignCircuitState {
  key: string;
  phase: SovereignCircuitPhase;
  failures: number;
  openedAt: number | null;
  lastFailureAt: number | null;
  halfOpenAttempts: number;
}

export interface SovereignCircuitTransition {
  state: SovereignCircuitState;
  changed: boolean;
  reason: string;
}

export const DEFAULT_SOVEREIGN_CIRCUIT_POLICY: SovereignCircuitPolicy = {
  failureThreshold: 3,
  cooldownMs: 30_000,
  halfOpenMaxAttempts: 1,
};

function positiveInteger(value: unknown, fallback: number): number {
  return Number.isInteger(value) && Number(value) > 0 ? Number(value) : fallback;
}

export function normalizeSovereignCircuitPolicy(policy: Partial<SovereignCircuitPolicy> = {}): SovereignCircuitPolicy {
  return {
    failureThreshold: positiveInteger(policy.failureThreshold, DEFAULT_SOVEREIGN_CIRCUIT_POLICY.failureThreshold),
    cooldownMs: positiveInteger(policy.cooldownMs, DEFAULT_SOVEREIGN_CIRCUIT_POLICY.cooldownMs),
    halfOpenMaxAttempts: positiveInteger(policy.halfOpenMaxAttempts, DEFAULT_SOVEREIGN_CIRCUIT_POLICY.halfOpenMaxAttempts),
  };
}

export function createSovereignCircuitState(key: string): SovereignCircuitState {
  const cleanKey = key.trim();
  if (!cleanKey) throw new Error('Circuit key is required.');

  return {
    key: cleanKey,
    phase: 'closed',
    failures: 0,
    openedAt: null,
    lastFailureAt: null,
    halfOpenAttempts: 0,
  };
}

export function refreshSovereignCircuitState(
  state: SovereignCircuitState,
  policy: Partial<SovereignCircuitPolicy> = {},
  nowMs = Date.now(),
): SovereignCircuitTransition {
  const safePolicy = normalizeSovereignCircuitPolicy(policy);

  if (state.phase !== 'open' || state.openedAt === null) {
    return { state, changed: false, reason: 'Circuit refresh skipped.' };
  }

  if (nowMs - state.openedAt < safePolicy.cooldownMs) {
    return { state, changed: false, reason: 'Circuit cooldown is still active.' };
  }

  return {
    state: {
      ...state,
      phase: 'half-open',
      halfOpenAttempts: 0,
    },
    changed: true,
    reason: 'Circuit cooldown elapsed; half-open probe allowed.',
  };
}

export function canAttemptSovereignCircuit(
  state: SovereignCircuitState,
  policy: Partial<SovereignCircuitPolicy> = {},
  nowMs = Date.now(),
): boolean {
  const safePolicy = normalizeSovereignCircuitPolicy(policy);
  const refreshed = refreshSovereignCircuitState(state, safePolicy, nowMs).state;

  if (refreshed.phase === 'closed') return true;
  if (refreshed.phase === 'open') return false;
  return refreshed.halfOpenAttempts < safePolicy.halfOpenMaxAttempts;
}

export function recordSovereignCircuitAttempt(
  state: SovereignCircuitState,
  policy: Partial<SovereignCircuitPolicy> = {},
  nowMs = Date.now(),
): SovereignCircuitTransition {
  const safePolicy = normalizeSovereignCircuitPolicy(policy);
  const refreshed = refreshSovereignCircuitState(state, safePolicy, nowMs).state;

  if (refreshed.phase !== 'half-open') {
    return { state: refreshed, changed: refreshed !== state, reason: 'Attempt allowed without half-open counter change.' };
  }

  return {
    state: {
      ...refreshed,
      halfOpenAttempts: refreshed.halfOpenAttempts + 1,
    },
    changed: true,
    reason: 'Half-open probe attempt recorded.',
  };
}

export function recordSovereignCircuitSuccess(state: SovereignCircuitState): SovereignCircuitTransition {
  if (
    state.phase === 'closed'
    && state.failures === 0
    && state.openedAt === null
    && state.lastFailureAt === null
    && state.halfOpenAttempts === 0
  ) {
    return { state, changed: false, reason: 'Circuit is already healthy.' };
  }

  return {
    state: {
      ...state,
      phase: 'closed',
      failures: 0,
      openedAt: null,
      lastFailureAt: null,
      halfOpenAttempts: 0,
    },
    changed: true,
    reason: 'Circuit closed after success.',
  };
}

export function recordSovereignCircuitFailure(
  state: SovereignCircuitState,
  policy: Partial<SovereignCircuitPolicy> = {},
  nowMs = Date.now(),
): SovereignCircuitTransition {
  const safePolicy = normalizeSovereignCircuitPolicy(policy);
  const refreshed = refreshSovereignCircuitState(state, safePolicy, nowMs).state;
  const failures = refreshed.failures + 1;
  const opensCircuit = failures >= safePolicy.failureThreshold || refreshed.phase === 'half-open';

  return {
    state: {
      ...refreshed,
      phase: opensCircuit ? 'open' : 'closed',
      failures,
      openedAt: opensCircuit ? nowMs : refreshed.openedAt,
      lastFailureAt: nowMs,
      halfOpenAttempts: opensCircuit ? 0 : refreshed.halfOpenAttempts,
    },
    changed: true,
    reason: opensCircuit ? 'Circuit opened after repeated failures.' : 'Circuit failure recorded.',
  };
}

export function summarizeSovereignCircuit(state: SovereignCircuitState): string {
  const openedAt = state.openedAt === null ? 'never' : String(state.openedAt);
  const lastFailureAt = state.lastFailureAt === null ? 'never' : String(state.lastFailureAt);
  return `${state.key}: ${state.phase}, failures=${state.failures}, openedAt=${openedAt}, lastFailureAt=${lastFailureAt}`;
}
