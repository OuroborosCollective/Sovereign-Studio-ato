import { describe, expect, it } from 'vitest';
import {
  decideSovereignInternalOperator,
  type SovereignInternalOperatorSignal,
} from './sovereignInternalOperatorRuntime';
import { buildSovereignToolCapabilityRegistry } from '../features/product/runtime/sovereignToolCapabilityRuntime';

function capabilities(overrides: Partial<Parameters<typeof buildSovereignToolCapabilityRegistry>[0]> = {}) {
  return buildSovereignToolCapabilityRegistry({
    repoReady: true,
    githubAccessState: 'ready',
    githubTokenPresent: true,
    directPatchSupported: true,
    agentConfigured: true,
    workerAvailable: true,
    workspaceConfigured: true,
    draftPrSupported: true,
    activeExecutorStatus: 'idle',
    ...overrides,
  });
}

describe('sovereignInternalOperatorRuntime', () => {
  it('uses direct patch for small documentation changes', () => {
    const decision = decideSovereignInternalOperator({
      intent: 'direct_patch',
      taskComplexity: 'simple',
      capabilities: capabilities(),
      traceIdProvider: () => 'test-direct',
    });

    expect(decision.state).toBe('allowed');
    expect(decision.route).toBe('direct_patch');
    expect(decision.nextAction).toBe('run_direct_patch');
    expect(decision.stages).toContain('diff_guard');
    expect(decision.stages).toContain('draft_pr_gate');
  });

  it('prefers the own workspace before the optional Sovereign Agent bridge', () => {
    const decision = decideSovereignInternalOperator({
      intent: 'code_execution',
      taskComplexity: 'complex',
      capabilities: capabilities({ directPatchSupported: false }),
      traceIdProvider: () => 'test-workspace',
    });

    expect(decision.state).toBe('allowed');
    expect(decision.route).toBe('internal_workspace');
    expect(decision.nextAction).toBe('start_workspace');
    expect(decision.stages).toContain('test_selection');
  });

  it('blocks when no evidence-backed patch executor route exists', () => {
    const decision = decideSovereignInternalOperator({
      intent: 'code_execution',
      taskComplexity: 'complex',
      capabilities: capabilities({
        directPatchSupported: false,
        agentConfigured: false,
        workspaceConfigured: false,
      }),
      traceIdProvider: () => 'test-internal',
    });

    expect(decision.state).toBe('blocked');
    expect(decision.route).toBe('blocked');
    expect(decision.nextAction).toBe('show_blocker');
    expect(decision.reason).toContain('Keine sichere interne Operator-Route');
    expect(decision.stages).toEqual([]);
  });

  it('blocks hard when repo or write access is not ready', () => {
    const decision = decideSovereignInternalOperator({
      intent: 'code_execution',
      taskComplexity: 'complex',
      capabilities: capabilities({
        githubAccessState: 'missing',
        githubTokenPresent: false,
      }),
      traceIdProvider: () => 'test-blocked',
    });

    expect(decision.state).toBe('blocked');
    expect(decision.route).toBe('blocked');
    expect(decision.nextAction).toBe('show_blocker');
    expect(decision.confidence).toBe(0);
  });

  it('lets learning signals adjust confidence but not bypass guards', () => {
    const signals: SovereignInternalOperatorSignal[] = [
      { route: 'internal_runtime_patch', accepted: true, weight: 1 },
    ];

    const decision = decideSovereignInternalOperator({
      intent: 'code_execution',
      taskComplexity: 'complex',
      capabilities: capabilities({
        directPatchSupported: false,
        agentConfigured: false,
        workspaceConfigured: false,
      }),
      internalRuntimePatchConfigured: true,
      signals,
      traceIdProvider: () => 'test-learning',
    });

    expect(decision.state).toBe('blocked');
    expect(decision.route).toBe('blocked');
    expect(decision.learningDelta).toBe(0);
    expect(decision.confidence).toBe(0);
  });
});
