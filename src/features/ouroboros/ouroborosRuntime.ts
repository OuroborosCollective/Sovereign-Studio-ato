import type { OuroborosGuardReport, OuroborosState } from './ouroborosSlice';

export type OuroborosValidationResult =
  | { readonly valid: true; readonly violations: readonly [] }
  | { readonly valid: false; readonly violations: readonly string[] };

export interface OuroborosRuntimeReportOptions {
  readonly checkedAt?: number;
}

const VIOLATION = {
  AUTH_WITHOUT_INIT: 'AUTH_WITHOUT_INIT: isAuthSequenceActive=true requires isRootInitialized=true',
  ORPHANED_ARE: 'ORPHANED_ARE: activeAREPayload requires isAuthSequenceActive=true',
  RESONANCE_CONSENT_MISMATCH: 'RESONANCE_CONSENT_MISMATCH: resonance.consentGranted=true conflicts with activePattern.consentLevel=none',
  CONSENT_NONE_WITH_TIMESTAMP: 'CONSENT_NONE_WITH_TIMESTAMP: consentLevel=none requires grantedAt=null',
  CONSENT_REVOKE_WITHOUT_GRANT: 'CONSENT_REVOKE_WITHOUT_GRANT: revokedAt requires grantedAt',
} as const;

function positiveTimestampViolation(field: string, value: number): string {
  return `${field.toUpperCase()}_TIMESTAMP_INVALID: ${field}=${value} must be > 0`;
}

function resonanceStrengthViolation(value: number): string {
  return `RESONANCE_STRENGTH_BOUNDS: strength=${value} must be between 0 and 1`;
}

function reinforcementCountViolation(value: number): string {
  return `RESONANCE_COUNT_NEGATIVE: reinforcementCount=${value} must be >= 0`;
}

function consentActiveWithoutTimestamp(level: string): string {
  return `CONSENT_ACTIVE_WITHOUT_TIMESTAMP: consentLevel=${level} requires grantedAt`;
}

function consentRevokeOrderViolation(grantedAt: number, revokedAt: number): string {
  return `CONSENT_REVOKE_ORDER: revokedAt=${revokedAt} must be > grantedAt=${grantedAt}`;
}

function checkAuthInvariants(state: OuroborosState, violations: string[]): void {
  if (state.isAuthSequenceActive && !state.isRootInitialized) {
    violations.push(VIOLATION.AUTH_WITHOUT_INIT);
  }

  if (state.activeAREPayload !== null && !state.isAuthSequenceActive) {
    violations.push(VIOLATION.ORPHANED_ARE);
  }
}

function checkResonanceInvariants(state: OuroborosState, violations: string[]): void {
  const resonance = state.resonance;
  if (resonance === null) return;

  if (resonance.strength < 0 || resonance.strength > 1) {
    violations.push(resonanceStrengthViolation(resonance.strength));
  }

  if (resonance.reinforcementCount < 0) {
    violations.push(reinforcementCountViolation(resonance.reinforcementCount));
  }

  if (resonance.lastReinforced <= 0) {
    violations.push(positiveTimestampViolation('lastReinforced', resonance.lastReinforced));
  }

  if (resonance.consentGranted && state.activePattern?.consentLevel === 'none') {
    violations.push(VIOLATION.RESONANCE_CONSENT_MISMATCH);
  }
}

function checkConsentInvariants(state: OuroborosState, violations: string[]): void {
  const activePattern = state.activePattern;
  if (activePattern === null) return;

  if (activePattern.consentLevel === 'none' && activePattern.grantedAt !== null) {
    violations.push(VIOLATION.CONSENT_NONE_WITH_TIMESTAMP);
  }

  if (activePattern.consentLevel !== 'none' && activePattern.grantedAt === null) {
    violations.push(consentActiveWithoutTimestamp(activePattern.consentLevel));
  }

  if (activePattern.revokedAt !== null && activePattern.grantedAt === null) {
    violations.push(VIOLATION.CONSENT_REVOKE_WITHOUT_GRANT);
  }

  if (activePattern.revokedAt !== null && activePattern.grantedAt !== null && activePattern.revokedAt <= activePattern.grantedAt) {
    violations.push(consentRevokeOrderViolation(activePattern.grantedAt, activePattern.revokedAt));
  }
}

function checkTelemetryInvariants(state: OuroborosState, violations: string[]): void {
  const telemetry = state.telemetry;
  if (telemetry === null) return;

  if (telemetry.timestamp <= 0) {
    violations.push(positiveTimestampViolation('telemetry', telemetry.timestamp));
  }
}

export function validateOuroborosState(state: OuroborosState): OuroborosValidationResult {
  const violations: string[] = [];

  checkAuthInvariants(state, violations);
  checkResonanceInvariants(state, violations);
  checkConsentInvariants(state, violations);
  checkTelemetryInvariants(state, violations);

  if (violations.length > 0) return { valid: false, violations };
  return { valid: true, violations: [] };
}

export function assertOuroborosStateValid(state: OuroborosState): asserts state is OuroborosState {
  const result = validateOuroborosState(state);
  if (result.valid) return;

  throw new Error([
    `[OuroborosRuntime] ${result.violations.length} invariant violation(s)`,
    ...result.violations.map((violation, index) => `${index + 1}. ${violation}`),
  ].join('\n'));
}

function stateForStableHash(state: OuroborosState): Omit<OuroborosState, 'guardReport'> {
  const { guardReport: _guardReport, ...hashable } = state;
  return hashable;
}

export function buildOuroborosRuntimeReport(
  state: OuroborosState,
  options: OuroborosRuntimeReportOptions = {},
): OuroborosGuardReport {
  const checkedAt = options.checkedAt ?? Date.now();
  const result = validateOuroborosState(state);

  return {
    isValid: result.valid,
    violations: result.violations,
    checkedAt,
    stateHash: djb2Hex(stableStringify(stateForStableHash(state))),
  };
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;

  const record = value as Record<string, unknown>;
  const body = Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(',');
  return `{${body}}`;
}

function djb2Hex(input: string): string {
  let hash = 5381;
  for (let index = 0; index < input.length; index += 1) {
    hash = ((hash << 5) + hash) ^ input.charCodeAt(index);
    hash >>>= 0;
  }
  return hash.toString(16).padStart(8, '0');
}
