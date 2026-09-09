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
  const returnedRunId = id(body.runId ?? run.runId ?? run.run_id, /^run-[0-9a-f]{32}$/);
  const approvals = Array.isArray(body.approvals) ? body.approvals.map(record) : [];
  return {
    route, method, httpStatus, requestedRunId, returnedRunId,
    identityMatches: requestedRunId && returnedRunId ? requestedRunId === returnedRunId : null,
    status: code(run.status ?? job.status ?? body.status),
    jobId: id(run.jobId ?? run.job_id ?? body.jobId ?? job.id, /^[A-Za-z][A-Za-z0-9-]{2,119}$/),
    evidenceId: id(run.evidenceId ?? body.evidenceId, /^evidence-[0-9a-f]{32}$/),
    failureFamily: code(body.failureFamily ?? body.failure_family ?? body.blocker),
    nextAction: code(run.nextAction ?? run.next_action ?? body.nextAction),
    approvals: approvals.map(approval => ({
      runId: id(approval.run_id, /^run-[0-9a-f]{32}$/),
      kind: code(approval.kind), status: code(approval.status),
      requiresProtectedOwnerInput: approval.requiresProtectedOwnerInput === true,
    })),
  };
}
