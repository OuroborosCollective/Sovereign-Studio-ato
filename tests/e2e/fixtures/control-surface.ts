import { createHash } from 'node:crypto';

// HTTP adapter fixture for browser regressions. This is never production or
// runtime evidence; real store/schema behavior is covered by PostgreSQL tests.
export function controlSurfaceFixture(jobId: string | null = null, mode: 'free' | 'paid' = 'free') {
  const observedAt = new Date().toISOString();
  const integration = { id: 'postgresql', name: 'PostgreSQL', status: 'verified',
    source: 'enterprise-platform-readback', observedAt, boundary: 'Browser-test HTTP fixture', blocker: null };
  const readbackSha256 = createHash('sha256')
    .update(JSON.stringify(integration, Object.keys(integration).sort())).digest('hex');
  return {
    schemaVersion: 'sovereign.control-surface-readback.v1', jobId, observedAt,
    jobExecutionMode: jobId ? mode : null,
    agentReadbackState: 'live', integrationReadbackState: 'live',
    agents: [{ id: 'sovereign-local-runner', name: 'sovereign-local-runner', kind: 'executor',
      status: jobId ? 'BLOCKED' : 'DECLARED',
      source: jobId ? 'sovereign-agent-jobs' : 'repository-execution-manifest',
      ...(jobId ? { jobId } : {}), description: 'Browser-test executor projection; no SDK execution is implied.' }],
    integrations: [{ ...integration, readbackSha256 }],
    credits: { readbackState: 'live', credits: 9, providerFundedCredits: 9,
      creditStateVerified: true, paidEntitlementVerified: true, paidEntitlementSource: 'purchase-fixture' },
    routing: { repositoryMode: 'free', agentMode: 'single', modes: [
      { mode: 'free', available: true, providerAvailable: true, model: 'free-fixture',
        routeId: 'free-fixture', profileId: 'free_single_agent' },
      { mode: 'paid', available: true, providerAvailable: true, model: 'paid-fixture',
        routeId: 'paid-fixture', profileId: 'paid_swarm_6' },
    ] },
  };
}
