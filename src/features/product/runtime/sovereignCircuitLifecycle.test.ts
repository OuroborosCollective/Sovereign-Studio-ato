import { describe, expect, it } from 'vitest';
import {
  canAttemptSovereignCircuit,
  createSovereignCircuitState,
  recordSovereignCircuitAttempt,
  recordSovereignCircuitFailure,
  recordSovereignCircuitSuccess,
  refreshSovereignCircuitState,
} from './sovereignCircuitLifecycle';

describe('sovereignCircuitLifecycle', () => {
  it('starts closed and allows attempts', () => {
    const state = createSovereignCircuitState('tab:repo');

    expect(state.phase).toBe('closed');
    expect(canAttemptSovereignCircuit(state)).toBe(true);
  });

  it('opens after the configured failure threshold', () => {
    const policy = { failureThreshold: 2, cooldownMs: 1000, halfOpenMaxAttempts: 1 };
    const first = recordSovereignCircuitFailure(createSovereignCircuitState('tab:remote'), policy, 1000).state;
    const second = recordSovereignCircuitFailure(first, policy, 1100).state;

    expect(first.phase).toBe('closed');
    expect(second.phase).toBe('open');
    expect(canAttemptSovereignCircuit(second, policy, 1200)).toBe(false);
  });

  it('transitions to half-open after cooldown', () => {
    const policy = { failureThreshold: 1, cooldownMs: 1000, halfOpenMaxAttempts: 1 };
    const open = recordSovereignCircuitFailure(createSovereignCircuitState('tab:workflow'), policy, 1000).state;
    const refreshed = refreshSovereignCircuitState(open, policy, 2500).state;

    expect(open.phase).toBe('open');
    expect(refreshed.phase).toBe('half-open');
    expect(canAttemptSovereignCircuit(refreshed, policy, 2500)).toBe(true);
  });

  it('limits half-open probe attempts', () => {
    const policy = { failureThreshold: 1, cooldownMs: 1000, halfOpenMaxAttempts: 1 };
    const open = recordSovereignCircuitFailure(createSovereignCircuitState('tab:workflow'), policy, 1000).state;
    const refreshed = refreshSovereignCircuitState(open, policy, 2500).state;
    const attempted = recordSovereignCircuitAttempt(refreshed, policy, 2500).state;

    expect(attempted.halfOpenAttempts).toBe(1);
    expect(canAttemptSovereignCircuit(attempted, policy, 2501)).toBe(false);
  });

  it('closes and resets after a successful render', () => {
    const policy = { failureThreshold: 1, cooldownMs: 1000, halfOpenMaxAttempts: 1 };
    const open = recordSovereignCircuitFailure(createSovereignCircuitState('tab:diff'), policy, 1000).state;
    const closed = recordSovereignCircuitSuccess(open).state;

    expect(closed.phase).toBe('closed');
    expect(closed.failures).toBe(0);
    expect(closed.openedAt).toBeNull();
    expect(closed.lastFailureAt).toBeNull();
  });
});
