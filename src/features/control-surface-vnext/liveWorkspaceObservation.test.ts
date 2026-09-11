import { describe, expect, it } from 'vitest';
import { runtimeObservation } from '../../../tests/e2e/helpers/live-runtime-observation';

describe('workspace failure is retained from real backend response fields', () => {
  it('preserves missing diff/test/tool evidence without inventing execution success', () => {
    const observed = runtimeObservation('/api/user/agent/swarm/run', 'POST', 503, {
      status: 'BLOCKED', repositoryExecutionPerformed: false,
      jobEvidence: { gatePassed: false, canPrepareDraftPr: false, changedFiles: [], hasDiff: false, hasTests: false, gateReason: 'No changed files - evidence gate requires generated files' },
      repositoryTools: { rolesWithCalls: [], rolesWithMutations: [] },
    });
    expect(observed?.repositoryExecution).toEqual({ performed: false, gatePassed: false, canPrepareDraftPr: false, gateFailure: 'CHANGED_FILES_MISSING', changedFileCount: 0, hasDiff: false, hasTests: false, toolCallingRoleCount: 0, mutatingRoleCount: 0, freeAgentCalledTools: false });
  });
  it('does not turn missing or string booleans into false/true evidence', () => {
    const result = runtimeObservation('/api/user/agent/swarm/run', 'POST', 503, { jobEvidence: { gatePassed: 'true' } });
    expect(result?.repositoryExecution.gatePassed).toBeNull();
    expect(result?.repositoryExecution.hasTests).toBeNull();
    expect(result?.repositoryExecution.changedFileCount).toBeNull();
    expect(result?.execution.repositoryExecutionAllowed).toBeNull();
  });
  it('retains real backend test-evidence failure after real mutations', () => {
    const result = runtimeObservation('/api/user/agent/swarm/run', 'POST', 503, { jobEvidence: { gatePassed: false, gateReason: 'No test summary - Draft PR preparation requires test evidence', changedFiles: ['README.md'], hasDiff: true, hasTests: false }, repositoryTools: { rolesWithCalls: ['free_single_agent'], rolesWithMutations: ['free_single_agent'] } });
    expect(result?.repositoryExecution).toMatchObject({ gateFailure: 'TEST_EVIDENCE_MISSING', changedFileCount: 1, freeAgentCalledTools: true, mutatingRoleCount: 1 });
  });
  it('does not leak raw gate reasons, file paths, role strings or credential-shaped job IDs', () => {
    const secret = 'sk-' + 'synthetic-unit-only'.repeat(3);
    const result = runtimeObservation('/api/user/agent/swarm/run', 'POST', 503, { jobId: secret, jobEvidence: { gateReason: secret, changedFiles: [secret] }, repositoryTools: { rolesWithCalls: [secret], rolesWithMutations: [secret] } });
    expect(result?.jobId).toBeNull();
    expect(result?.repositoryExecution.gateFailure).toBeNull();
    expect(JSON.stringify(result)).not.toContain(secret);
  });
  it('projects the free single-agent execution identity and internal workspace without copying route secrets', () => {
    const secret = 'sk-' + 'synthetic-route-secret'.repeat(3);
    const result = runtimeObservation('/api/user/agent/swarm/run', 'POST', 200, {
      runId: 'run-' + 'a'.repeat(32),
      jobId: 'job-abcd1234',
      workspaceId: 'workspace-1234',
      maxBackgroundAgents: 0,
      repositoryExecutionPerformed: true,
      executionResolution: {
        profileId: 'free_single_agent',
        requestedMode: 'free',
        resolvedTransport: 'freellm',
        resolvedTransportClass: 'FREELLM_FREE',
        billingCategory: 'free',
        candidateRouteIds: ['route-a', 'route-b'],
        maxForegroundAgents: 1,
        maxBackgroundAgents: 0,
        repositoryExecutionAllowed: true,
        secretValuesReturned: false,
        providerModel: secret,
      },
      jobEvidence: { gatePassed: true, canPrepareDraftPr: true, changedFiles: ['README.md'], hasDiff: true, hasTests: true, gateReason: 'Evidence gate passed - all checks complete' },
      repositoryTools: {
        callsByRole: { free_single_agent: 4 },
        mutationsByRole: { free_single_agent: 1 },
        rolesWithCalls: ['free_single_agent'],
        rolesWithMutations: ['free_single_agent'],
        writeConfirmed: true,
      },
    });
    expect(result).toMatchObject({
      workspaceId: 'workspace-1234',
      execution: {
        profileId: 'free_single_agent', requestedMode: 'free', resolvedTransport: 'freellm',
        resolvedTransportClass: 'FREELLM_FREE', billingCategory: 'free', candidateRouteCount: 2,
        maxForegroundAgents: 1, maxBackgroundAgents: 0, repositoryExecutionAllowed: true,
        secretValuesReturned: false, responseMaxBackgroundAgents: 0,
      },
      toolDiagnostics: { callCount: 4, mutationCount: 1, writeConfirmed: true },
      repositoryExecution: { performed: true, gatePassed: true, canPrepareDraftPr: true, changedFileCount: 1, hasDiff: true, hasTests: true, freeAgentCalledTools: true },
    });
    expect(JSON.stringify(result)).not.toContain(secret);
  });
});
