import { describe, expect, it } from 'vitest';
import {
  assertOuroborosStateValid,
  buildOuroborosRuntimeReport,
  validateOuroborosState,
} from './ouroborosRuntime';
import type { OuroborosState } from './ouroborosSlice';

const VALID_STATE: OuroborosState = {
  isAuthSequenceActive: false,
  activeAREPayload: null,
  errorState: null,
  isRootInitialized: true,
  telemetry: {
    eventType: 'root_init',
    timestamp: 1_700_000_000_000,
    sequenceId: 'seq-root',
    source: 'system',
  },
  resonance: null,
  guardReport: null,
  activePattern: null,
};

function withState(overrides: Partial<OuroborosState>): OuroborosState {
  return { ...VALID_STATE, ...overrides };
}

describe('validateOuroborosState', () => {
  it('accepts a valid initialized state', () => {
    expect(validateOuroborosState(VALID_STATE)).toEqual({ valid: true, violations: [] });
  });

  it('rejects active auth before root initialization', () => {
    const result = validateOuroborosState(withState({ isAuthSequenceActive: true, isRootInitialized: false }));
    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.violations.join('\n')).toContain('AUTH_WITHOUT_INIT');
  });

  it('rejects orphaned ARE payloads', () => {
    const result = validateOuroborosState(withState({ activeAREPayload: { isActive: true }, isAuthSequenceActive: false }));
    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.violations.join('\n')).toContain('ORPHANED_ARE');
  });

  it('rejects resonance bounds and invalid timestamps', () => {
    const result = validateOuroborosState(withState({
      resonance: {
        patternId: 'pattern-1',
        strength: 1.2,
        lastReinforced: 0,
        consentGranted: false,
        reinforcementCount: -1,
      },
    }));

    expect(result.valid).toBe(false);
    if (!result.valid) {
      const text = result.violations.join('\n');
      expect(text).toContain('RESONANCE_STRENGTH_BOUNDS');
      expect(text).toContain('LASTREINFORCED_TIMESTAMP_INVALID');
      expect(text).toContain('RESONANCE_COUNT_NEGATIVE');
    }
  });

  it('rejects resonance consent mismatch', () => {
    const result = validateOuroborosState(withState({
      resonance: {
        patternId: 'pattern-1',
        strength: 0.7,
        lastReinforced: 1_700_000_000_001,
        consentGranted: true,
        reinforcementCount: 1,
      },
      activePattern: {
        patternId: 'pattern-1',
        consentLevel: 'none',
        grantedAt: null,
        revokedAt: null,
      },
    }));

    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.violations.join('\n')).toContain('RESONANCE_CONSENT_MISMATCH');
  });

  it('rejects invalid consent timestamp combinations', () => {
    const result = validateOuroborosState(withState({
      activePattern: {
        patternId: 'pattern-1',
        consentLevel: 'session',
        grantedAt: 1_700_000_000_003,
        revokedAt: 1_700_000_000_002,
      },
    }));

    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.violations.join('\n')).toContain('CONSENT_REVOKE_ORDER');
  });

  it('rejects invalid telemetry timestamps', () => {
    const result = validateOuroborosState(withState({
      telemetry: {
        eventType: 'auth_start',
        timestamp: 0,
        sequenceId: 'seq-bad',
        source: 'system',
      },
    }));

    expect(result.valid).toBe(false);
    if (!result.valid) expect(result.violations.join('\n')).toContain('TELEMETRY_TIMESTAMP_INVALID');
  });
});

describe('assertOuroborosStateValid', () => {
  it('does not throw for a valid state', () => {
    expect(() => assertOuroborosStateValid(VALID_STATE)).not.toThrow();
  });

  it('throws a structured runtime error for invalid state', () => {
    expect(() => assertOuroborosStateValid(withState({ isAuthSequenceActive: true, isRootInitialized: false })))
      .toThrow(/OuroborosRuntime/);
  });
});

describe('buildOuroborosRuntimeReport', () => {
  it('builds a deterministic serializable report for a fixed checkedAt', () => {
    const report = buildOuroborosRuntimeReport(VALID_STATE, { checkedAt: 1_700_000_000_010 });

    expect(report).toEqual({
      isValid: true,
      violations: [],
      checkedAt: 1_700_000_000_010,
      stateHash: expect.stringMatching(/^[0-9a-f]{8}$/),
    });
  });

  it('excludes the previous guardReport from the state hash', () => {
    const first = buildOuroborosRuntimeReport(VALID_STATE, { checkedAt: 1_700_000_000_010 });
    const stateWithReport = { ...VALID_STATE, guardReport: first };
    const second = buildOuroborosRuntimeReport(stateWithReport, { checkedAt: 1_700_000_000_020 });

    expect(second.stateHash).toBe(first.stateHash);
  });
});
