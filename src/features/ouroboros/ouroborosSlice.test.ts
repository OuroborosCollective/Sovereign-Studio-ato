import { describe, expect, it } from 'vitest';
import reducer, {
  clearActivePattern,
  clearError,
  grantPatternConsent,
  initializeRoot,
  recordTelemetry,
  revokePatternConsent,
  setAREPayload,
  setGuardReport,
  startAuthSequence,
  stopAuthSequence,
  triggerError,
  updateResonance,
  type AREPayload,
  type OuroborosState,
} from './ouroborosSlice';
import { buildOuroborosRuntimeReport } from './ouroborosRuntime';

const initialState: OuroborosState = {
  isAuthSequenceActive: false,
  activeAREPayload: null,
  errorState: null,
  isRootInitialized: false,
  telemetry: null,
  resonance: null,
  guardReport: null,
  activePattern: null,
};

describe('ouroborosSlice reducers', () => {
  it('starts and stops the auth sequence', () => {
    const started = reducer(initialState, startAuthSequence());
    expect(started.isAuthSequenceActive).toBe(true);

    const withPayload = reducer(started, setAREPayload({ isActive: true }));
    const stopped = reducer(withPayload, stopAuthSequence());
    expect(stopped.isAuthSequenceActive).toBe(false);
    expect(stopped.activeAREPayload).toBeNull();
  });

  it('stores and clears ARE payloads', () => {
    const payload: AREPayload = { isActive: true };
    const withPayload = reducer(initialState, setAREPayload(payload));
    expect(withPayload.activeAREPayload).toEqual(payload);

    const cleared = reducer(withPayload, setAREPayload(null));
    expect(cleared.activeAREPayload).toBeNull();
  });

  it('initializes root with typed telemetry', () => {
    const nextState = reducer(initialState, initializeRoot({
      sessionId: 'session-1',
      source: 'boot',
      initialTelemetry: {
        eventType: 'root_init',
        timestamp: 1_700_000_000_000,
        sequenceId: 'seq-root',
        source: 'system',
      },
    }));

    expect(nextState.isRootInitialized).toBe(true);
    expect(nextState.telemetry?.eventType).toBe('root_init');
  });

  it('handles error state', () => {
    const failed = reducer(initialState, triggerError('Invalid root hash'));
    expect(failed.errorState).toBe('Invalid root hash');

    const cleared = reducer(failed, clearError());
    expect(cleared.errorState).toBeNull();
  });

  it('records typed telemetry', () => {
    const nextState = reducer(initialState, recordTelemetry({
      eventType: 'auth_start',
      timestamp: 1_700_000_000_001,
      sequenceId: 'seq-auth',
      source: 'user',
      metadata: { route: 'AuthRoot' },
    }));

    expect(nextState.telemetry?.sequenceId).toBe('seq-auth');
  });

  it('updates resonance using reducer payload timestamp instead of Date.now inside the reducer', () => {
    const nextState = reducer(initialState, updateResonance({
      patternId: 'pattern-1',
      strength: 1.5,
      lastReinforced: 1_700_000_000_002,
      consentGranted: true,
      reinforcementCount: 3.8,
    }));

    expect(nextState.resonance).toEqual({
      patternId: 'pattern-1',
      strength: 1,
      lastReinforced: 1_700_000_000_002,
      consentGranted: true,
      reinforcementCount: 3,
    });
  });

  it('stores and revokes pattern consent', () => {
    const granted = reducer(initialState, grantPatternConsent({
      patternId: 'pattern-1',
      consentLevel: 'session',
      grantedAt: 1_700_000_000_003,
    }));

    expect(granted.activePattern?.consentLevel).toBe('session');
    expect(granted.activePattern?.revokedAt).toBeNull();

    const revoked = reducer(granted, revokePatternConsent({
      patternId: 'pattern-1',
      revokedAt: 1_700_000_000_004,
    }));
    expect(revoked.activePattern?.revokedAt).toBe(1_700_000_000_004);

    const cleared = reducer(revoked, clearActivePattern());
    expect(cleared.activePattern).toBeNull();
  });

  it('stores a runtime guard report', () => {
    const rooted = reducer(initialState, initializeRoot({ sessionId: 'session-1', source: 'boot' }));
    const report = buildOuroborosRuntimeReport(rooted, { checkedAt: 1_700_000_000_010 });
    const nextState = reducer(rooted, setGuardReport(report));

    expect(nextState.guardReport?.isValid).toBe(true);
    expect(nextState.guardReport?.checkedAt).toBe(1_700_000_000_010);
    expect(nextState.guardReport?.stateHash).toMatch(/^[0-9a-f]{8}$/);
  });
});
