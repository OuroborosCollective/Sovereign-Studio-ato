import { describe, expect, it } from 'vitest';
import {
  canUseSovereignDependency,
  createSovereignDependencyLifecycleState,
  recordSovereignDependencyFailure,
  recordSovereignDependencySuccess,
  refreshSovereignDependencyLifecycle,
  startSovereignDependencyCheck,
} from './sovereignDependencyLifecycle';

describe('sovereignDependencyLifecycle', () => {
  it('starts idle and can begin a dependency check', () => {
    const initial = createSovereignDependencyLifecycleState('github-api', 'github');
    const started = startSovereignDependencyCheck(initial, {}, 1000).state;

    expect(initial.phase).toBe('idle');
    expect(started.phase).toBe('checking');
    expect(started.checkedAt).toBe(1000);
    expect(canUseSovereignDependency(started, {}, 1001)).toBe(true);
  });

  it('records success and marks stale dependencies as degraded', () => {
    const ready = recordSovereignDependencySuccess(
      startSovereignDependencyCheck(createSovereignDependencyLifecycleState('workflow-watch', 'workflow'), {}, 1000).state,
      'Workflow API reachable.',
      1100,
    ).state;
    const stale = refreshSovereignDependencyLifecycle(ready, { staleAfterMs: 1000 }, 3000).state;

    expect(ready.phase).toBe('ready');
    expect(stale.phase).toBe('degraded');
    expect(stale.message).toContain('stale');
  });

  it('opens the dependency circuit after repeated failures', () => {
    const policy = { failureThreshold: 2, cooldownMs: 1000, halfOpenMaxAttempts: 1, staleAfterMs: 5000 };
    const first = recordSovereignDependencyFailure(
      createSovereignDependencyLifecycleState('remote-gateway', 'remote-memory'),
      policy,
      'Gateway timeout.',
      1000,
    ).state;
    const second = recordSovereignDependencyFailure(first, policy, 'Gateway timeout again.', 1100).state;

    expect(first.phase).toBe('degraded');
    expect(second.phase).toBe('blocked');
    expect(second.circuit.phase).toBe('open');
    expect(canUseSovereignDependency(second, policy, 1200)).toBe(false);
  });

  it('allows half-open recovery after cooldown and closes on success', () => {
    const policy = { failureThreshold: 1, cooldownMs: 1000, halfOpenMaxAttempts: 1, staleAfterMs: 5000 };
    const blocked = recordSovereignDependencyFailure(
      createSovereignDependencyLifecycleState('pattern-store', 'pattern-memory'),
      policy,
      'Store failed.',
      1000,
    ).state;
    const recovering = refreshSovereignDependencyLifecycle(blocked, policy, 2500).state;
    const started = startSovereignDependencyCheck(recovering, policy, 2500).state;
    const ready = recordSovereignDependencySuccess(started, 'Pattern store recovered.', 2600).state;

    expect(recovering.phase).toBe('recovering');
    expect(started.phase).toBe('recovering');
    expect(ready.phase).toBe('ready');
    expect(ready.circuit.phase).toBe('closed');
    expect(ready.circuit.failures).toBe(0);
  });

  it('keeps an open dependency blocked during cooldown', () => {
    const policy = { failureThreshold: 1, cooldownMs: 10_000, halfOpenMaxAttempts: 1, staleAfterMs: 5000 };
    const blocked = recordSovereignDependencyFailure(
      createSovereignDependencyLifecycleState('github-pr', 'github'),
      policy,
      'GitHub unavailable.',
      1000,
    ).state;
    const refreshed = refreshSovereignDependencyLifecycle(blocked, policy, 5000).state;

    expect(refreshed.phase).toBe('blocked');
    expect(canUseSovereignDependency(refreshed, policy, 5000)).toBe(false);
  });
});
