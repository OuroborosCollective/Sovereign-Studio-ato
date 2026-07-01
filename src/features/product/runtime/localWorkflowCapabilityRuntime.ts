/**
 * Local Workflow Capability Runtime — Issue #447
 * Evaluates whether a learned pattern qualifies as locally executable.
 * No fake state. All checks must pass to grant local capability.
 */

export interface LocalCapabilityCheckInput {
  readonly inputsValidatable: boolean;
  readonly stepsDeterministic: boolean;
  readonly noSecretTokensRequired: boolean;
  readonly noMandatoryLlmRoute: boolean;
  readonly resultVerifiable: boolean;
  readonly hasTestsOrReplayChecks: boolean;
}

export interface LocalCapabilityCheckResult {
  readonly localExecutable: boolean;
  readonly passedChecks: string[];
  readonly failedChecks: string[];
  readonly summary: string;
}

export interface LocalWorkflowCapabilityState {
  readonly patternId: string;
  readonly checks: LocalCapabilityCheckInput;
  readonly evaluatedAt: number;
  readonly result: LocalCapabilityCheckResult;
}

export interface LocalWorkflowCapabilityStore {
  readonly version: 1;
  readonly states: LocalWorkflowCapabilityState[];
  readonly updatedAt: number;
}

const CHECK_LABELS: Record<keyof LocalCapabilityCheckInput, string> = {
  inputsValidatable: 'Eingaben validierbar',
  stepsDeterministic: 'Schritte deterministisch oder regelbasiert',
  noSecretTokensRequired: 'Keine geheimen Tokens erforderlich',
  noMandatoryLlmRoute: 'Keine zwingend nötige LLM-Route',
  resultVerifiable: 'Ergebnis prüfbar',
  hasTestsOrReplayChecks: 'Tests oder Replay-Checks vorhanden',
};

const MAX_STATES = 500;

export function evaluateLocalCapability(checks: LocalCapabilityCheckInput): LocalCapabilityCheckResult {
  const passedChecks: string[] = [];
  const failedChecks: string[] = [];

  for (const [key, label] of Object.entries(CHECK_LABELS) as [keyof LocalCapabilityCheckInput, string][]) {
    if (checks[key]) {
      passedChecks.push(label);
    } else {
      failedChecks.push(label);
    }
  }

  const localExecutable = failedChecks.length === 0;

  const summary = localExecutable
    ? `Lokal ausführbar — alle ${passedChecks.length} Checks bestanden.`
    : `Nicht lokal ausführbar — ${failedChecks.length} Check(s) nicht erfüllt: ${failedChecks.join('; ')}.`;

  return { localExecutable, passedChecks, failedChecks, summary };
}

export function buildLocalWorkflowCapabilityState(
  patternId: string,
  checks: LocalCapabilityCheckInput,
  now = Date.now(),
): LocalWorkflowCapabilityState {
  if (!patternId.trim()) {
    throw new Error('patternId is required for local workflow capability state.');
  }
  const result = evaluateLocalCapability(checks);
  return { patternId, checks, evaluatedAt: now, result };
}

export function createLocalWorkflowCapabilityStore(now = Date.now()): LocalWorkflowCapabilityStore {
  return { version: 1, states: [], updatedAt: now };
}

export function upsertLocalWorkflowCapabilityState(
  store: LocalWorkflowCapabilityStore,
  state: LocalWorkflowCapabilityState,
  now = Date.now(),
): LocalWorkflowCapabilityStore {
  const existing = store.states.find((s) => s.patternId === state.patternId);
  const nextStates = existing
    ? store.states.map((s) => s.patternId === state.patternId ? state : s)
    : [state, ...store.states].slice(0, MAX_STATES);

  return { version: 1, states: nextStates, updatedAt: now };
}

export function getLocalWorkflowCapabilityState(
  store: LocalWorkflowCapabilityStore,
  patternId: string,
): LocalWorkflowCapabilityState | null {
  return store.states.find((s) => s.patternId === patternId) ?? null;
}

export function queryLocalExecutableStates(store: LocalWorkflowCapabilityStore): LocalWorkflowCapabilityState[] {
  return store.states.filter((s) => s.result.localExecutable);
}

export function buildLocalCapabilityCheckSummary(checks: LocalCapabilityCheckInput): string {
  const result = evaluateLocalCapability(checks);
  return result.summary;
}

export function validateLocalCapabilityCheckInput(checks: LocalCapabilityCheckInput): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  const keys: (keyof LocalCapabilityCheckInput)[] = [
    'inputsValidatable',
    'stepsDeterministic',
    'noSecretTokensRequired',
    'noMandatoryLlmRoute',
    'resultVerifiable',
    'hasTestsOrReplayChecks',
  ];
  for (const key of keys) {
    if (typeof checks[key] !== 'boolean') {
      errors.push(`Check '${key}' must be a boolean.`);
    }
  }
  return { valid: errors.length === 0, errors };
}
