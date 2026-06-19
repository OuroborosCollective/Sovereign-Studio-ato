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

export interface SovereignDependencyLifecycleTransition {
  state: SovereignDependencyLifecycleState;
  changed: boolean;
  reason: string;
}

export interface SovereignDependencyLifecyclePolicy extends SovereignCircuitPolicy {
  staleAfterMs: number;
}

export const DEFAULT_SOVEREIGN_DEPENDENCY_POLICY: SovereignDependencyLifecyclePolicy = {
  ...DEFAULT_SOVEREIGN_CIRCUIT_POLICY,
  staleAfterMs: 5 * 60_000,
};

function normalizeKey(value: string): string {
  const key = value.trim();
  if (!key) throw new Error('Dependency key is required.');
  return key;
}

function normalizePolicy(policy: Partial<SovereignDependencyLifecyclePolicy> = {}): SovereignDependencyLifecyclePolicy {
  const staleAfterMs = Number.isInteger(policy.staleAfterMs) && Number(policy.staleAfterMs) > 0
    ? Number(policy.staleAfterMs)
    : DEFAULT_SOVEREIGN_DEPENDENCY_POLICY.staleAfterMs;

  return {
    ...DEFAULT_SOVEREIGN_DEPENDENCY_POLICY,
    ...policy,
    staleAfterMs,
  };
}

export function createSovereignDependencyLifecycleState(
  key: string,
  kind: SovereignDependencyKind,
  message = 'Dependency has not been checked yet.',
): SovereignDependencyLifecycleState {
  const normalizedKey = normalizeKey(key);

  return {
    key: normalizedKey,
    kind,
    phase: 'idle',
    circuit: createSovereignCircuitState(`dependency:${normalizedKey}`),
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
  const safePolicy = normalizePolicy(policy);
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
  const refreshed = refreshSovereignDependencyLifecycle(state, policy, nowMs).state;
  return refreshed.phase !== 'blocked' && canAttemptSovereignCircuit(refreshed.circuit, normalizePolicy(policy), nowMs);
}

export function startSovereignDependencyCheck(
  state: SovereignDependencyLifecycleState,
  policy: Partial<SovereignDependencyLifecyclePolicy> = {},
  nowMs = Date.now(),
): SovereignDependencyLifecycleTransition {
  const refreshed = refreshSovereignDependencyLifecycle(state, policy, nowMs).state;
  if (!canUseSovereignDependency(refreshed, policy, nowMs)) {
    return {
      state: refreshed,
      changed: refreshed !== state,
      reason: 'Dependency check blocked by open circuit.',
    };
  }

  const attempt = recordSovereignCircuitAttempt(refreshed.circuit, normalizePolicy(policy), nowMs).state;
  return {
    state: {
      ...refreshed,
      phase: attempt.phase === 'half-open' ? 'recovering' : 'checking',
      circuit: attempt,
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
  const circuit = recordSovereignCircuitFailure(state.circuit, normalizePolicy(policy), nowMs).state;

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
