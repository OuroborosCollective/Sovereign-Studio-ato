import { describe, it, expect } from 'vitest';
import reducer, { setTelemetry, setResonance, initializeRoot, triggerError, clearError } from './ouroborosSlice';

describe('ouroboros slice', () => {
  it('should return the initial state', () => {
    expect(reducer(undefined, { type: 'unknown' })).toEqual({
      telemetry: {
        sysLoad: 14,
        resSync: 10.00,
        latency: 12,
        uplinkStatus: 'ACTIVE',
      },
      resonance: 0.842,
      isRootInitialized: false,
      kappaPosHash: '',
      errorState: false,
    });
  });

  it('should handle initializeRoot', () => {
    const actual = reducer(undefined, initializeRoot('0x12345678'));
    expect(actual.isRootInitialized).toBe(true);
    expect(actual.kappaPosHash).toBe('0x12345678');
  });

  it('should handle triggerError', () => {
    const actual = reducer(undefined, triggerError());
    expect(actual.errorState).toBe(true);
  });
});
