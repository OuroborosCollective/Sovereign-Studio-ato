import type { ControlSurfaceReadback, IntegrationAttachment, RuntimeAgentNode } from '../types/domain';

type Row = Record<string, unknown>;
function record(value: unknown): Row {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Control surface readback returned an invalid object.');
  return value as Row;
}
function string(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error('Control surface readback returned an invalid identity.');
  return value;
}
function timestamp(value: unknown): string {
  const text = string(value);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(text) || !Number.isFinite(Date.parse(text))) throw new Error('Control surface readback returned an invalid timestamp.');
  return text;
}
function optionalString(value: unknown): string | undefined { return value == null ? undefined : string(value); }
function state(value: unknown): 'live' | 'unavailable' {
  if (value !== 'live' && value !== 'unavailable') throw new Error('Control surface readback state is invalid.');
  return value;
}
function boolean(value: unknown): boolean {
  if (typeof value !== 'boolean') throw new Error('Control surface readback returned an invalid availability.');
  return value;
}
function balance(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Control surface credit readback is invalid.');
  return value;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error('Control surface readback returned an invalid list.');
  return value;
}

export function parseControlSurfaceReadback(value: unknown, requestedJobId?: string): ControlSurfaceReadback {
  const body = record(value);
  if (body.schemaVersion !== 'sovereign.control-surface-readback.v1'
      || body.jobId !== (requestedJobId || null)) throw new Error('Control surface readback schema or job binding is invalid.');
  const observedAt = timestamp(body.observedAt);
  const agents = array(body.agents).map((value): RuntimeAgentNode => {
    const row = record(value);
    if (row.kind !== 'executor' && row.kind !== 'agent') throw new Error('Agent readback kind is invalid.');
    const source = string(row.source);
    const jobId = optionalString(row.jobId);
    if (jobId !== requestedJobId || !['repository-execution-manifest', 'sovereign-agent-jobs', 'agents-sdk'].includes(source)
        || (!requestedJobId && (source !== 'repository-execution-manifest' || row.status !== 'DECLARED'))
        || (row.kind === 'agent' && (source !== 'agents-sdk' || !row.runId || !row.taskId))) {
      throw new Error('Agent readback owner/job/source binding is invalid.');
    }
    return { id: string(row.id), name: string(row.name), kind: row.kind, source, jobId,
      status: string(row.status), persistedStatus: optionalString(row.persistedStatus), description: string(row.description),
      runId: optionalString(row.runId), taskId: optionalString(row.taskId),
      createdAt: row.createdAt == null ? undefined : timestamp(row.createdAt),
      updatedAt: row.updatedAt == null ? undefined : timestamp(row.updatedAt) };
  });
  const integrations = array(body.integrations).map((value): IntegrationAttachment => {
    const row = record(value);
    const status = string(row.status);
    if (!['verified', 'blocked', 'degraded', 'isolated', 'defined_not_run'].includes(status)
        || row.source !== 'enterprise-platform-readback' || !/^[a-f0-9]{64}$/.test(string(row.readbackSha256))) {
      throw new Error('Integration readback provenance is invalid.');
    }
    return { id: string(row.id), name: string(row.name), status: status as IntegrationAttachment['status'],
      source: row.source, observedAt: timestamp(row.observedAt), boundary: optionalString(row.boundary),
      blocker: optionalString(row.blocker), readbackSha256: string(row.readbackSha256) };
  });
  const rawCredits = record(body.credits);
  const creditState = state(rawCredits.readbackState);
  let credits: ControlSurfaceReadback['credits'];
  if (creditState === 'live') {
    const amount = balance(rawCredits.credits);
    const funded = balance(rawCredits.providerFundedCredits);
    if (rawCredits.creditStateVerified !== true || funded > amount) throw new Error('Control surface credit readback verification failed.');
    credits = { readbackState: 'live', creditStateVerified: true, credits: amount, providerFundedCredits: funded,
      paidEntitlementVerified: boolean(rawCredits.paidEntitlementVerified), paidEntitlementSource: string(rawCredits.paidEntitlementSource) };
  } else {
    credits = { readbackState: 'unavailable', creditStateVerified: false, blocker: string(rawCredits.blocker) };
  }
  const rawRouting = record(body.routing);
  if (rawRouting.repositoryMode !== 'free' || rawRouting.agentMode !== 'single') throw new Error('Repository route readback policy is invalid.');
  const modes = array(rawRouting.modes).map((value): ControlSurfaceReadback['routing']['modes'][number] => {
    const row = record(value);
    if (row.mode !== 'free' && row.mode !== 'paid') throw new Error('Route readback mode is invalid.');
    const available = boolean(row.available);
    const providerAvailable = boolean(row.providerAvailable);
    if ((available && !providerAvailable) || (row.mode === 'paid' && available
        && (credits.creditStateVerified !== true || !credits.providerFundedCredits || !credits.paidEntitlementVerified))) {
      throw new Error('Route readback contradicts the repository execution or billing contract.');
    }
    return { mode: row.mode, available, providerAvailable, model: optionalString(row.model), routeId: optionalString(row.routeId),
      profileId: optionalString(row.profileId), blocker: optionalString(row.blocker), executionBlocker: optionalString(row.executionBlocker) };
  });
  if (modes.length !== 2 || new Set(modes.map(row => row.mode)).size !== 2) throw new Error('Route readback must identify Free and Paid availability.');
  const agentReadbackState = state(body.agentReadbackState);
  const integrationReadbackState = state(body.integrationReadbackState);
  if ((agentReadbackState === 'unavailable' && agents.length) || (integrationReadbackState === 'unavailable' && integrations.length)) {
    throw new Error('Control surface readback contradicts unavailable registry state.');
  }
  return { schemaVersion: body.schemaVersion, jobId: requestedJobId || null, observedAt, receivedMonotonicMs: performance.now(),
    jobExecutionMode: body.jobExecutionMode === 'free' || body.jobExecutionMode === 'paid' ? body.jobExecutionMode : undefined,
    agents, agentReadbackState, agentBlocker: optionalString(body.agentBlocker), integrations, integrationReadbackState,
    integrationBlocker: optionalString(body.integrationBlocker), credits, routing: { repositoryMode: 'free', agentMode: 'single', modes } };
}
