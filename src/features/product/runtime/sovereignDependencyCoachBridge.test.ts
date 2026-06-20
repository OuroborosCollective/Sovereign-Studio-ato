// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buildSovereignDependencyCoachSignal,
  publishSovereignDependencyCoachSignal,
} from './sovereignDependencyCoachBridge';
import {
  createSovereignDependencyLifecycleState,
  recordSovereignDependencyFailure,
  recordSovereignDependencySuccess,
  startSovereignDependencyCheck,
} from './sovereignDependencyLifecycle';

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as Window & typeof globalThis & { __sovereignRuntimeCoachState?: unknown }).__sovereignRuntimeCoachState;
});

describe('sovereignDependencyCoachBridge', () => {
  it('maps idle dependencies to a yellow waiting signal', () => {
    const idle = createSovereignDependencyLifecycleState('repo-tree', 'github', 'GitHub repository tree has not been checked yet.');
    const signal = buildSovereignDependencyCoachSignal(idle);

    expect(signal.lamp).toBe('yellow');
    expect(signal.thinking).toBe(false);
    expect(signal.dependencyPhase).toBe('idle');
    expect(signal.telemetryLabel).toBe('dependency:github:idle');
    expect(signal.telemetryLevel).toBe('info');
  });

  it('maps ready dependencies to a green success signal', () => {
    const started = startSovereignDependencyCheck(createSovereignDependencyLifecycleState('repo-tree', 'github'), {}, 100).state;
    const ready = recordSovereignDependencySuccess(started, 'Repo loaded.', 200).state;
    const signal = buildSovereignDependencyCoachSignal(ready);

    expect(signal.lamp).toBe('green');
    expect(signal.thinking).toBe(false);
    expect(signal.dependencyPhase).toBe('ready');
    expect(signal.telemetryLabel).toBe('dependency:github:ready');
    expect(signal.telemetryLevel).toBe('success');
  });

  it('maps degraded dependencies to yellow warning signals', () => {
    const started = startSovereignDependencyCheck(createSovereignDependencyLifecycleState('workflow-watch', 'workflow'), {}, 100).state;
    const degraded = recordSovereignDependencyFailure(started, { failureThreshold: 3 }, 'Endpoint returned 503.', 200).state;
    const signal = buildSovereignDependencyCoachSignal(degraded);

    expect(signal.lamp).toBe('yellow');
    expect(signal.dependencyPhase).toBe('degraded');
    expect(signal.telemetryLabel).toBe('dependency:workflow:degraded');
    expect(signal.telemetryLevel).toBe('warning');
  });

  it('maps blocked dependencies to red error signals', () => {
    const blocked = recordSovereignDependencyFailure(
      createSovereignDependencyLifecycleState('remote-gateway', 'remote-memory'),
      { failureThreshold: 1 },
      'Gateway unavailable.',
      200,
    ).state;
    const signal = buildSovereignDependencyCoachSignal(blocked);

    expect(signal.lamp).toBe('red');
    expect(signal.dependencyPhase).toBe('blocked');
    expect(signal.telemetryLabel).toBe('dependency:remote-memory:blocked');
    expect(signal.telemetryLevel).toBe('error');
  });

  it('publishes runtime coach and dependency events', () => {
    const dependency = recordSovereignDependencySuccess(
      startSovereignDependencyCheck(createSovereignDependencyLifecycleState('repo-tree', 'github'), {}, 100).state,
      'Repo loaded.',
      200,
    ).state;
    const dependencyListener = vi.fn();
    const telemetryListener = vi.fn();
    const coachListener = vi.fn();

    window.addEventListener('sovereign:dependency-lifecycle-state', dependencyListener);
    window.addEventListener('sovereign:dependency-telemetry-event', telemetryListener);
    window.addEventListener('sovereign:runtime-coach-state', coachListener);

    const signal = publishSovereignDependencyCoachSignal(dependency, 300);
    const assigned = (window as Window & typeof globalThis & { __sovereignRuntimeCoachState?: unknown }).__sovereignRuntimeCoachState as Record<string, unknown>;

    expect(signal.telemetryLabel).toBe('dependency:github:ready');
    expect(assigned.title).toBe(signal.title);
    expect(assigned.updatedAt).toBe(300);
    expect(dependencyListener).toHaveBeenCalledTimes(1);
    expect(telemetryListener).toHaveBeenCalledTimes(1);
    expect(coachListener).toHaveBeenCalledTimes(1);

    window.removeEventListener('sovereign:dependency-lifecycle-state', dependencyListener);
    window.removeEventListener('sovereign:dependency-telemetry-event', telemetryListener);
    window.removeEventListener('sovereign:runtime-coach-state', coachListener);
  });
});
