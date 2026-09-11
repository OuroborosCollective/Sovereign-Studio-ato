/** Allowlisted observations of actual backend responses; no credential, prompt or raw error serialization. */
function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}
function id(value: unknown, pattern: RegExp): string | null {
  return typeof value === 'string' && pattern.test(value) ? value : null;
}
function code(value: unknown): string | null {
  if (typeof value !== 'string' || /^(?:svk_|sva_|sk_|sk-|ghp_|ghs_|gho_|github_pat_|hf_|eyJ)/i.test(value)) return null;
  return /^[A-Za-z][A-Za-z0-9_:-]{1,119}$/.test(value) ? value : null;
}
function boundedIdentifier(value: unknown): string | null {
  if (typeof value !== 'string' || /^(?:svk_|sva_|sk_|sk-|ghp_|ghs_|gho_|github_pat_|hf_|eyJ)/i.test(value)) return null;
  return /^[A-Za-z0-9][A-Za-z0-9._:-]{1,159}$/.test(value) ? value : null;
}
function exactGithubRepositoryUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try {
    const parsed = new URL(value);
    const segments = parsed.pathname.split('/').filter(Boolean);
    if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || segments.length !== 2) return null;
    return `https://github.com/${segments[0]}/${segments[1].replace(/\.git$/i, '')}`;
  } catch {
    return null;
  }
}

function nonNegativeInteger(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

// A model may quote a tool error, but its text is NEVER authoritative runtime evidence.
function modelFailureHints(value: unknown): string[] {
  if (typeof value !== 'string') return [];
  const known: Record<string, string> = {
    MCP_RUNTIME_REVISION_MISMATCH: 'installed MCP revision differs from the backend source revision',
    MCP_REVISION_UNVERIFIED: 'installed MCP revision is not authoritatively verified',
    MCP_IMAGE_DIGEST_UNVERIFIED: 'installed MCP image digest is not authoritatively verified',
    MCP_CONTROL_PLANE_NOT_READY: 'MCP protocol or broker readback is not ready',
    BROKER_SOCKET_UNAVAILABLE: 'authoritative MCP broker socket is unavailable',
    BROKER_SOCKET_PERMISSION_DENIED: 'backend cannot read the authoritative MCP broker socket',
    BROKER_RPC_TIMEOUT: 'authoritative MCP revision readback timed out',
    GIT_READBACK_FAILED: 'authoritative Git readback failed',
  };
  return Object.entries(known).filter(([failureCode, message]) => value.includes(failureCode) || value.includes(message)).map(([failureCode]) => failureCode);
}

function flag(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}
function count(value: unknown): number | null {
  return Array.isArray(value) ? value.length : null;
}
function gateFailure(value: unknown): string | null {
  const reasons: Record<string, string> = {
    'No changed files - evidence gate requires generated files': 'CHANGED_FILES_MISSING',
    'No diff summary - evidence gate requires git diff': 'DIFF_MISSING',
    'No test summary - Draft PR preparation requires test evidence': 'TEST_EVIDENCE_MISSING',
    'Evidence gate passed - all checks complete': 'PASSED',
  };
  return typeof value === 'string' && Object.hasOwn(reasons, value) ? reasons[value] : null;
}

/** Secret-safe projection of the actual browser request. Mission/evidence/credentials are never serialized. */
export function runRequestObservation(path: string, method: string, payload: unknown) {
  if (path !== '/api/user/agent/swarm/run' || method !== 'POST') return null;
  const body = record(payload);
  return {
    route: 'swarm.start.request',
    mode: code(body.mode),
    agentMode: code(body.agentMode),
    intentMode: code(body.intentMode),
    repositoryUrl: exactGithubRepositoryUrl(body.repositoryUrl),
    repositoryBranch: code(body.repositoryBranch),
  };
}

export function runtimeObservation(path: string, method: string, httpStatus: number, payload: unknown) {
  let route: string;
  let requestedRunId: string | null = null;
  if (path === '/api/user/agent/swarm/run' && method === 'POST') route = 'swarm.start';
  else if (/^\/api\/user\/agent\/swarm\/runs\/run-[0-9a-f]{32}$/.test(path) && method === 'GET') {
    route = 'swarm.read'; requestedRunId = path.split('/').pop()!;
  } else if (/^\/api\/user\/agent\/jobs\/[A-Za-z0-9-]{3,120}$/.test(path) && method === 'GET') route = 'job.read';
  else if (path === '/api/controller/approvals' && method === 'GET') route = 'approval.read';
  else return null;
  const body = record(payload);
  const run = record(body.run);
  const job = record(body.job);
  const jobEvidence = record(body.jobEvidence);
  const repositoryTools = record(body.repositoryTools);
  const executionResolution = record(body.executionResolution);
  const returnedRunId = id(body.runId ?? run.runId ?? run.run_id, /^run-[0-9a-f]{32}$/);
  const approvals = Array.isArray(body.approvals) ? body.approvals.map(record) : [];
  return {
    route, method, httpStatus, requestedRunId, returnedRunId,
    identityMatches: requestedRunId && returnedRunId ? requestedRunId === returnedRunId : null,
    status: code(run.status ?? job.status ?? body.status),
    jobId: id(run.jobId ?? run.job_id ?? body.jobId ?? job.jobId ?? job.id ?? body.id, /^(?:agent|job)-[0-9a-f-]{4,100}$/),
    workspaceId: boundedIdentifier(body.workspaceId ?? job.workspaceId),
    evidenceId: id(run.evidenceId ?? body.evidenceId, /^evidence-[0-9a-f]{32}$/),
    failureFamily: code(body.failureFamily ?? body.failure_family ?? body.blocker),
    nextAction: code(run.nextAction ?? run.next_action ?? body.nextAction),
    execution: {
      profileId: code(executionResolution.profileId),
      requestedMode: code(executionResolution.requestedMode),
      resolvedTransport: code(executionResolution.resolvedTransport),
      resolvedTransportClass: code(executionResolution.resolvedTransportClass),
      billingCategory: code(executionResolution.billingCategory),
      candidateRouteCount: count(executionResolution.candidateRouteIds),
      maxForegroundAgents: nonNegativeInteger(executionResolution.maxForegroundAgents),
      maxBackgroundAgents: nonNegativeInteger(executionResolution.maxBackgroundAgents),
      repositoryExecutionAllowed: flag(executionResolution.repositoryExecutionAllowed),
      secretValuesReturned: flag(executionResolution.secretValuesReturned),
      responseMaxBackgroundAgents: nonNegativeInteger(body.maxBackgroundAgents),
    },
    toolDiagnostics: {
      callCount: nonNegativeInteger(record(repositoryTools.callsByRole).free_single_agent),
      mutationCount: nonNegativeInteger(record(repositoryTools.mutationsByRole).free_single_agent),
      consecutiveFailureCount: nonNegativeInteger(record(repositoryTools.consecutiveFailuresByRole).free_single_agent),
      circuitOpen: Array.isArray(repositoryTools.openCircuits)
        ? repositoryTools.openCircuits.includes('free_single_agent') : null,
      writeConfirmed: flag(repositoryTools.writeConfirmed),
      jobEventCount: count(job.events ?? body.events),
    },
    nonAuthoritativeModelHints: {
      source: 'model-output-not-runtime-proof',
      failureFamilies: modelFailureHints(record(body.result).assistant_text),
    },
    repositoryExecution: {
      performed: flag(body.repositoryExecutionPerformed),
      gatePassed: flag(jobEvidence.gatePassed),
      canPrepareDraftPr: flag(jobEvidence.canPrepareDraftPr),
      gateFailure: gateFailure(jobEvidence.gateReason),
      changedFileCount: count(jobEvidence.changedFiles ?? job.changedFiles ?? body.changedFiles),
      hasDiff: flag(jobEvidence.hasDiff),
      hasTests: flag(jobEvidence.hasTests),
      toolCallingRoleCount: count(repositoryTools.rolesWithCalls),
      mutatingRoleCount: count(repositoryTools.rolesWithMutations),
      freeAgentCalledTools: Array.isArray(repositoryTools.rolesWithCalls)
        ? repositoryTools.rolesWithCalls.includes('free_single_agent') : null,
    },
    approvals: approvals.map(approval => ({
      runId: id(approval.run_id, /^run-[0-9a-f]{32}$/),
      kind: code(approval.kind), status: code(approval.status),
      requiresProtectedOwnerInput: approval.requiresProtectedOwnerInput === true,
    })),
  };
}
