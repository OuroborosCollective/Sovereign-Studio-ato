import { describe, expect, it } from 'vitest';
import { decideRouteFailover } from './routeFailoverRuntime';

describe('routeFailoverRuntime', () => {
  it('routes status questions locally without starting worker or executor', () => {
    const decision = decideRouteFailover({
      taskKind: 'status',
      workerAvailable: false,
      githubWriteReady: false,
      agentReady: false,
      directPatchAvailable: false,
      activeBlocker: 'Worker HTTP 500',
    });

    expect(decision.kind).toBe('local_status');
    expect(decision.route).toBe('runtime');
    expect(decision.event.state).toBe('done');
    expect(decision.nextAction).toContain('keinen Worker');
  });

  it('blocks write routes at GitHub access before fallback tries worker chat', () => {
    const decision = decideRouteFailover({
      taskKind: 'small_patch',
      workerAvailable: true,
      githubWriteReady: false,
      agentReady: true,
      directPatchAvailable: true,
    });

    expect(decision.allowed).toBe(false);
    expect(decision.route).toBe('github-access');
    expect(decision.event.kind).toBe('blocked');
  });

  it('prefers direct github patch for small patch when write access and direct patch are ready', () => {
    const decision = decideRouteFailover({
      taskKind: 'small_patch',
      workerAvailable: true,
      githubWriteReady: true,
      agentReady: false,
      directPatchAvailable: true,
    });

    expect(decision.allowed).toBe(true);
    expect(decision.route).toBe('direct-github-patch');
  });

  it('falls back from direct patch to Sovereign Agent for small patch when executor is ready', () => {
    const decision = decideRouteFailover({
      taskKind: 'small_patch',
      workerAvailable: true,
      githubWriteReady: true,
      agentReady: true,
      directPatchAvailable: false,
    });

    expect(decision.allowed).toBe(true);
    expect(decision.route).toBe('sovereign-agent');
  });

  it('honestly blocks complex work when executor is unavailable', () => {
    const decision = decideRouteFailover({
      taskKind: 'complex_patch',
      workerAvailable: true,
      githubWriteReady: true,
      agentReady: false,
      directPatchAvailable: true,
    });

    expect(decision.allowed).toBe(false);
    expect(decision.route).toBe('sovereign-agent');
    expect(decision.event.state).toBe('blocked');
  });
});
