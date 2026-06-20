import {
  DEFAULT_SOVEREIGN_CIRCUIT_POLICY,
  canAttemptSovereignCircuit,
  createSovereignCircuitState,
  recordSovereignCircuitAttempt,
  recordSovereignCircuitFailure,
  recordSovereignCircuitSuccess,
  refreshSovereignCircuitState,
  summarizeSovereignCircuit,
  type SovereignCircuitPolicy,
  type SovereignCircuitState,
} from './sovereignCircuitLifecycle';

export type SovereignDependencyKind = 'github' | 'remote-memory' | 'pattern-memory' | 'workflow' | 'runtime' | 'telemetry' | 'custom';
export type SovereignDependencyPhase = 'idle' | 'checking' | 'ready' | 'degraded' | 'blocked' | 'recovering';

export interface SovereignDependencyLifecycleState {
  key: string;
  kind: SovereignDependencyKind;
  phase: SovereignDependencyPhase;
  circuit: SovereignCircuitState;
  checkedAt: number | null;
  lastSuccessAt: number | null;
  lastFailureAt: number | null;
  message: string;
}

export interface SovereignDependencyLifecyclePolicy extends SovereignCircuitPolicy {
  staleAfterMs: number;
}

export interface SovereignDependencyLifecycleTransition {
  state: SovereignDependencyLifecycleState;
  changed: boolean;
  reason: string;
}

export const DEFAULT_SOVEREIGN_DEPENDENCY_POLICY: SovereignDependencyLifecyclePolicy = {
  ...DEFAULT_SOVEREIGN_CIRCUIT_POLICY,
  staleAfterMs: 5 * 60_000,
};

function positiveInteger(value: unknown, fallback: number): number {
  return Number.isInteger(value) && Number(value) > 0 ? Number(value) : fallback;
}

function normalizeDependencyPolicy(policy: Partial<SovereignDependencyLifecyclePolicy> = {}): SovereignDependencyLifecyclePolicy {
  return {
    ...DEFAULT_SOVEREIGN_DEPENDENCY_POLICY,
    ...policy,
    failureThreshold: positiveInteger(policy.failureThreshold, DEFAULT_SOVEREIGN_DEPENDENCY_POLICY.failureThreshold),
    cooldownMs: positiveInteger(policy.cooldownMs, DEFAULT_SOVEREIGN_DEPENDENCY_POLICY.cooldownMs),
    halfOpenMaxAttempts: positiveInteger(policy.halfOpenMaxAttempts, DEFAULT_SOVEREIGN_DEPENDENCY_POLICY.halfOpenMaxAttempts),
    staleAfterMs: positiveInteger(policy.staleAfterMs, DEFAULT_SOVEREIGN_DEPENDENCY_POLICY.staleAfterMs),
  };
}

export function createSovereignDependencyLifecycleState(
  key: string,
  kind: SovereignDependencyKind,
  message = 'Dependency has not been checked yet.',
): SovereignDependencyLifecycleState {
  const cleanKey = key.trim();
  if (!cleanKey) throw new Error('Dependency key is required.');

  return {
    key: cleanKey,
    kind,
    phase: 'idle',
    circuit: createSovereignCircuitState(`dependency:${cleanKey}`),
    checkedAt: null,
    lastSuccessAt: null,
    lastFailureAt: null,
    message,
  };
}

export function refreshSovereignDependencyLifecycle(
  state: SovereignDependencyLifecycleState,
  policy: Partial<SovereignDependencyLifecyclePolicy> = {},
  nowMs = Date.now(),
): SovereignDependencyLifecycleTransition {
  const safePolicy = normalizeDependencyPolicy(policy);
  const refreshedCircuit = refreshSovereignCircuitState(state.circuit, safePolicy, nowMs).state;
  let phase = state.phase;
  let message = state.message;

  if (refreshedCircuit.phase === 'open') {
    phase = 'blocked';
    message = 'Dependency circuit is open; waiting for cooldown.';
  } else if (refreshedCircuit.phase === 'half-open') {
    phase = 'recovering';
    message = 'Dependency circuit is half-open; one recovery probe is allowed.';
  } else if (state.lastSuccessAt !== null && nowMs - state.lastSuccessAt > safePolicy.staleAfterMs) {
    phase = 'degraded';
    message = 'Dependency check is stale and should be refreshed.';
  }

  const changed = refreshedCircuit !== state.circuit || phase !== state.phase || message !== state.message;
  return {
    state: changed ? { ...state, circuit: refreshedCircuit, phase, message } : state,
    changed,
    reason: changed ? 'Dependency lifecycle refreshed.' : 'Dependency lifecycle unchanged.',
  };
}

export function canUseSovereignDependency(
  state: SovereignDependencyLifecycleState,
  policy: Partial<SovereignDependencyLifecyclePolicy> = {},
  nowMs = Date.now(),
): boolean {
  const safePolicy = normalizeDependencyPolicy(policy);
  const refreshed = refreshSovereignDependencyLifecycle(state, safePolicy, nowMs).state;
  return refreshed.phase !== 'blocked' && canAttemptSovereignCircuit(refreshed.circuit, safePolicy, nowMs);
}

export function startSovereignDependencyCheck(
  state: SovereignDependencyLifecycleState,
  policy: Partial<SovereignDependencyLifecyclePolicy> = {},
  nowMs = Date.now(),
): SovereignDependencyLifecycleTransition {
  const safePolicy = normalizeDependencyPolicy(policy);
  const refreshed = refreshSovereignDependencyLifecycle(state, safePolicy, nowMs).state;

  if (!canUseSovereignDependency(refreshed, safePolicy, nowMs)) {
    return {
      state: refreshed,
      changed: refreshed !== state,
      reason: 'Dependency check blocked by open circuit.',
    };
  }

  const circuit = recordSovereignCircuitAttempt(refreshed.circuit, safePolicy, nowMs).state;

  return {
    state: {
      ...refreshed,
      phase: circuit.phase === 'half-open' ? 'recovering' : 'checking',
      circuit,
      checkedAt: nowMs,
      message: 'Dependency check started.',
    },
    changed: true,
    reason: 'Dependency check started.',
  };
}

export function recordSovereignDependencySuccess(
  state: SovereignDependencyLifecycleState,
  message = 'Dependency is ready.',
  nowMs = Date.now(),
): SovereignDependencyLifecycleTransition {
  const circuit = recordSovereignCircuitSuccess(state.circuit).state;

  return {
    state: {
      ...state,
      phase: 'ready',
      circuit,
      checkedAt: nowMs,
      lastSuccessAt: nowMs,
      message,
    },
    changed: true,
    reason: 'Dependency check succeeded.',
  };
}

export function recordSovereignDependencyFailure(
  state: SovereignDependencyLifecycleState,
  policy: Partial<SovereignDependencyLifecyclePolicy> = {},
  message = 'Dependency check failed.',
  nowMs = Date.now(),
): SovereignDependencyLifecycleTransition {
  const safePolicy = normalizeDependencyPolicy(policy);
  const circuit = recordSovereignCircuitFailure(state.circuit, safePolicy, nowMs).state;

  return {
    state: {
      ...state,
      phase: circuit.phase === 'open' ? 'blocked' : 'degraded',
      circuit,
      checkedAt: nowMs,
      lastFailureAt: nowMs,
      message,
    },
    changed: true,
    reason: circuit.phase === 'open' ? 'Dependency circuit opened after failure.' : 'Dependency failure recorded.',
  };
}

export function summarizeSovereignDependencyLifecycle(state: SovereignDependencyLifecycleState): string {
  return `${state.kind}:${state.key} phase=${state.phase} message=${state.message} circuit=${summarizeSovereignCircuit(state.circuit)}`;
}
