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
});
