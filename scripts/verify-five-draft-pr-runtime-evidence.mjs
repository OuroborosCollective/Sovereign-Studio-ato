import { readFileSync } from 'node:fs';

const EVIDENCE_PATH = process.argv[2] || 'test-results/five-draft-pr-evidence.json';
const document = JSON.parse(readFileSync(EVIDENCE_PATH, 'utf8'));
const fail = (message) => { throw new Error(`FIVE_PATH_RUNTIME_EVIDENCE_INVALID: ${message}`); };
const jobIdPattern = /^agent-[0-9a-f]{32}$/;
const a2aRefPattern = /^agent-zero-a2a:(?:retry:)?[A-Za-z0-9._:-]{1,200}$/;

if (!/^[0-9a-f]{40}$/.test(String(document.sourceRevision || ''))) fail('sourceRevision is not an exact Git SHA');
if (document.verifiedDraftPrCount !== 5 || !Array.isArray(document.evidence) || document.evidence.length !== 5) {
  fail(`expected exactly five verified Draft PRs, got ${document.verifiedDraftPrCount ?? 'missing'}`);
}
if (!Array.isArray(document.runtimeReadbacks)) fail('runtimeReadbacks missing');
if (document.omittedRuntimeReadbacks !== 0) fail(`runtime readbacks were truncated: ${document.omittedRuntimeReadbacks}`);
if (document.runtimeReadbacks.some((entry) => entry?.route === 'swarm.start')) {
  fail('repository evidence contains an unexpected Swarm start');
}

const backendOrigin = String(process.env.SOVEREIGN_E2E_BACKEND_PROXY_TARGET || '').trim();
let backendHealthUrl;
try {
  const parsed = new URL(backendOrigin);
  if (parsed.protocol !== 'https:' || !parsed.hostname || parsed.pathname !== '/') fail('backend proxy target must be an exact HTTPS origin');
  backendHealthUrl = new URL('/health', parsed);
} catch (error) {
  if (String(error?.message || '').startsWith('FIVE_PATH_RUNTIME_EVIDENCE_INVALID:')) throw error;
  fail('backend proxy target is invalid');
}
let runtimeHealthResponse;
try {
  runtimeHealthResponse = await fetch(backendHealthUrl, {
    headers: { 'Cache-Control': 'no-store' },
    signal: AbortSignal.timeout(30_000),
  });
} catch (error) {
  fail(`backend runtime identity readback failed: ${error?.name || 'FetchError'}`);
}
if (runtimeHealthResponse.status !== 200) fail(`backend runtime identity HTTP ${runtimeHealthResponse.status}`);
const runtimeHealth = await runtimeHealthResponse.json().catch(() => null);
if (!runtimeHealth || typeof runtimeHealth !== 'object' || runtimeHealth.status !== 'live') fail('backend runtime identity is not live');
const deployedRevision = String(runtimeHealth.sourceRevision || '').toLowerCase();
const deployedImageDigest = String(runtimeHealth.imageDigest || '').toLowerCase();
if (!/^[0-9a-f]{40}$/.test(deployedRevision)) fail('backend runtime sourceRevision is unverified');
if (!/^sha256:[0-9a-f]{64}$/.test(deployedImageDigest)) fail('backend runtime imageDigest is unverified');
if (deployedRevision !== document.sourceRevision) {
  fail(`evidence/runtime revision mismatch: evidence=${document.sourceRevision} runtime=${deployedRevision}`);
}

const validA2ARef = (value) => {
  const ref = String(value || '');
  return a2aRefPattern.test(ref) && !ref.includes(':claim:');
};

const seenJobs = new Set();
for (const item of document.evidence) {
  const jobId = String(item?.persistedJobId || '');
  if (!jobIdPattern.test(jobId)) fail('invalid persisted repository job id');
  if (seenJobs.has(jobId)) fail(`duplicate persisted repository job ${jobId}`);
  seenJobs.add(jobId);

  const request = item?.request || {};
  if (request.mode !== 'free') fail(`${jobId}: browser request mode ${request.mode}`);
  if (request.agentMode !== 'single') fail(`${jobId}: browser request agentMode ${request.agentMode}`);
  if (request.intentMode !== 'repository_execution') fail(`${jobId}: browser request intentMode ${request.intentMode}`);
  if (request.repositoryBranch !== 'main') fail(`${jobId}: browser request repositoryBranch ${request.repositoryBranch}`);
  if (!/^https:\/\/github\.com\/[^/]+\/[^/]+$/.test(String(request.repositoryUrl || ''))) fail(`${jobId}: browser request repository URL invalid`);

  const starts = document.runtimeReadbacks.filter((entry) => entry?.route === 'repository.start' && entry?.jobId === jobId);
  if (starts.length < 1) fail(`${jobId}: repository.start response missing`);
  if (starts.some((entry) => entry?.httpStatus !== 202)) fail(`${jobId}: repository.start was not HTTP 202`);
  const uniqueStartRefs = new Set(starts.map((entry) => String(entry?.externalRef || '')));
  if (uniqueStartRefs.size !== 1) fail(`${jobId}: start task binding was not stable`);
  const start = starts[0];
  if (!start.workspaceId) fail(`${jobId}: internal workspace id missing at start`);
  if (!validA2ARef(start.externalRef)) fail(`${jobId}: initial Agent Zero A2A binding invalid`);

  const execution = item?.execution || {};
  if (execution.jobId !== jobId) fail(`${jobId}: evidence/job identity mismatch`);
  if (execution.workspaceId !== start.workspaceId) fail(`${jobId}: evidence/workspace identity mismatch`);
  if (!validA2ARef(execution.externalRef)) fail(`${jobId}: serialized Agent Zero A2A binding invalid`);
  if (execution.prState !== 'ready') fail(`${jobId}: serialized prState is not ready`);
  if (!(execution.changedFileCount >= 1)) fail(`${jobId}: serialized changed-file evidence missing`);

  const reads = document.runtimeReadbacks.filter((entry) => entry?.route === 'job.read' && entry?.jobId === jobId);
  if (reads.length < 1) fail(`${jobId}: persisted job readback missing`);
  const readyReads = reads.filter((entry) => (
    entry?.httpStatus === 200
    && entry?.workspaceId === execution.workspaceId
    && entry?.prState === 'ready'
    && validA2ARef(entry?.externalRef)
    && (entry?.repositoryExecution?.changedFileCount || 0) >= 1
  ));
  if (readyReads.length < 1) fail(`${jobId}: READY_FOR_DRAFT_PR job readback missing`);
  const finalRead = readyReads.at(-1);
  if (finalRead.externalRef !== execution.externalRef) fail(`${jobId}: final A2A binding/evidence mismatch`);
  if (finalRead.repositoryExecution.changedFileCount !== execution.changedFileCount) fail(`${jobId}: final changed-file count/evidence mismatch`);

  if (item.draft !== true || item.stateAtVerification !== 'open' || item.readmeVerified !== true) fail(`${jobId}: GitHub Draft PR readback incomplete`);
  if (item.closedAfterVerification !== true || item.branchDeletedAfterVerification !== true) fail(`${jobId}: cleanup readback incomplete`);
}

console.log(JSON.stringify({
  ok: true,
  sourceRevision: document.sourceRevision,
  runtimeSourceRevision: deployedRevision,
  runtimeImageDigest: deployedImageDigest,
  verifiedJobs: seenJobs.size,
  invariant: 'exact-deployed-revision -> browser repository request -> persisted agent job -> one bounded Agent Zero A2A binding -> shared-workspace mutation -> Sovereign diff/regression/evidence closeout -> explicit consent -> verified Draft PR -> cleanup',
}, null, 2));
