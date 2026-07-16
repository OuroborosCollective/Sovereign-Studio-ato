import { describe, expect, it } from 'vitest';
import { decideSovereignExecutorBridgeRoute } from './sovereignExecutorBridgeRuntime';
import { buildSovereignToolCapabilityRegistry } from '../features/product/runtime/sovereignToolCapabilityRuntime';

describe('builder executor bridge migration contract', () => {
  it('defines the runtime call BuilderContainer must use for blocked code execution', () => {
    const decision = decideSovereignExecutorBridgeRoute({
      intent: 'code_execution',
      taskComplexity: 'complex',
      capabilities: buildSovereignToolCapabilityRegistry({
        repoReady: true,
        githubAccessState: 'ready',
        githubTokenPresent: true,
        directPatchSupported: false,
        agentConfigured: false,
        workerAvailable: true,
        workspaceConfigured: false,
        draftPrSupported: true,
        activeExecutorStatus: 'idle',
      }),
    });

    expect(decision.bridgeRoute).toBe('sovereign_internal_operator');
    expect(decision.state).toBe('blocked');
    expect(decision.nextAction).toBe('show_blocker');
    expect(decision.internalOperatorRoute).toBe('blocked');
    expect(decision.event.route).toBe('toolchain');
    expect(decision.event.state).toBe('blocked');
  });
});
