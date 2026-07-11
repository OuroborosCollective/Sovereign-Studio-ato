import { describe, expect, it } from 'vitest';
import { decideSovereignExecutorBridgeRoute } from './sovereignExecutorBridgeRuntime';
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

describe('sovereignExecutorBridgeRuntime', () => {
  it('keeps allowed executor decisions unchanged', () => {
    const decision = decideSovereignExecutorBridgeRoute({
      text: 'Bitte README Titel ändern',
      intent: 'direct_patch',
      capabilities: capabilities(),
      candidatePath: 'README.md',
    });

    expect(decision.bridgeRoute).toBe('executor_runtime');
    expect(decision.state).toBe('allowed');
    expect(decision.nextAction).toBe('run_direct_patch');
    expect(decision.executorRoute).toBe('direct_patch');
    expect(decision.executorActionRoute).toBe('direct-github-patch');
  });

  it('does not bypass missing GitHub write access', () => {
    const decision = decideSovereignExecutorBridgeRoute({
      text: 'Implementiere eine Runtime mit Tests',
      intent: 'code_execution',
      capabilities: capabilities({
        githubAccessState: 'missing',
        githubTokenPresent: false,
        directPatchSupported: false,
        agentConfigured: false,
        workspaceConfigured: false,
      }),
    });

    expect(decision.bridgeRoute).toBe('executor_runtime');
    expect(decision.state).toBe('blocked');
    expect(decision.reason).toContain('Schreib');
  });

  it('does not invent an internal operator execution route when no adapter is connected', () => {
    const decision = decideSovereignExecutorBridgeRoute({
      text: 'Baue internen Operator Fallback mit Tests',
      intent: 'code_execution',
      capabilities: capabilities({
        directPatchSupported: false,
        agentConfigured: false,
        workspaceConfigured: false,
      }),
    });

    expect(decision.bridgeRoute).toBe('sovereign_internal_operator');
    expect(decision.state).toBe('blocked');
    expect(decision.nextAction).toBe('show_blocker');
    expect(decision.internalOperatorRoute).toBe('blocked');
    expect(decision.reason).toContain('Keine sichere interne Operator-Route');
  });
});
