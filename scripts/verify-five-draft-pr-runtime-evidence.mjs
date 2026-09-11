import { readFileSync } from 'node:fs';

const EVIDENCE_PATH = 'test-results/five-draft-pr-evidence.json';
const document = JSON.parse(readFileSync(EVIDENCE_PATH, 'utf8'));
const fail = (message) => { throw new Error(`FIVE_PATH_RUNTIME_EVIDENCE_INVALID: ${message}`); };

if (!/^[0-9a-f]{40}$/.test(String(document.sourceRevision || ''))) fail('sourceRevision is not an exact Git SHA');
if (document.verifiedDraftPrCount !== 5 || !Array.isArray(document.evidence) || document.evidence.length !== 5) {
  fail(`expected exactly five verified Draft PRs, got ${document.verifiedDraftPrCount ?? 'missing'}`);
}
if (!Array.isArray(document.runtimeReadbacks)) fail('runtimeReadbacks missing');
if (document.omittedRuntimeReadbacks !== 0) fail(`runtime readbacks were truncated: ${document.omittedRuntimeReadbacks}`);

const seenRuns = new Set();
for (const item of document.evidence) {
  const runId = String(item?.persistedRunId || '');
  if (!/^run-[0-9a-f]{32}$/.test(runId)) fail('invalid persisted run id');
  if (seenRuns.has(runId)) fail(`duplicate persisted run ${runId}`);
  seenRuns.add(runId);

  const request = item?.request || {};
  if (request.mode !== 'free') fail(`${runId}: browser request mode ${request.mode}`);
  if (request.agentMode !== 'single') fail(`${runId}: browser request agentMode ${request.agentMode}`);
  if (request.intentMode !== 'repository_execution') fail(`${runId}: browser request intentMode ${request.intentMode}`);
  if (request.repositoryBranch !== 'main') fail(`${runId}: browser request repositoryBranch ${request.repositoryBranch}`);
  if (!/^https:\/\/github\.com\/[^/]+\/[^/]+$/.test(String(request.repositoryUrl || ''))) fail(`${runId}: browser request repository URL invalid`);

  const starts = document.runtimeReadbacks.filter((entry) => entry?.route === 'swarm.start' && entry?.returnedRunId === runId);
  if (starts.length !== 1) fail(`${runId}: expected one authoritative swarm.start response, got ${starts.length}`);
  const start = starts[0];
  const execution = start.execution || {};
  const repository = start.repositoryExecution || {};
  const tools = start.toolDiagnostics || {};
  const itemExecution = item?.execution || {};

  if (start.httpStatus !== 200) fail(`${runId}: start HTTP ${start.httpStatus}`);
  if (!start.jobId) fail(`${runId}: linked implementation job missing`);
  if (!start.workspaceId) fail(`${runId}: internal workspace id missing`);
  if (itemExecution.jobId !== start.jobId) fail(`${runId}: evidence/job identity mismatch`);
  if (itemExecution.workspaceId !== start.workspaceId) fail(`${runId}: evidence/workspace identity mismatch`);
  if (execution.profileId !== 'free_single_agent') fail(`${runId}: profile ${execution.profileId}`);
  if (execution.requestedMode !== 'free') fail(`${runId}: requested mode ${execution.requestedMode}`);
  if (!['FREELLM_FREE', 'OPENROUTER_FREE'].includes(execution.resolvedTransportClass)) fail(`${runId}: non-free transport class ${execution.resolvedTransportClass}`);
  if (execution.billingCategory !== 'free') fail(`${runId}: billing category ${execution.billingCategory}`);
  if (execution.maxForegroundAgents !== 1 || execution.maxBackgroundAgents !== 0 || execution.responseMaxBackgroundAgents !== 0) {
    fail(`${runId}: expected foreground=1/background=0`);
  }
  if (execution.repositoryExecutionAllowed !== true) fail(`${runId}: repository execution not allowed`);
  if (execution.secretValuesReturned !== false) fail(`${runId}: secret egress contract not explicitly false`);
  if (repository.performed !== true || repository.gatePassed !== true || repository.canPrepareDraftPr !== true) fail(`${runId}: repository evidence gate not proven`);
  if (!(repository.changedFileCount >= 1) || repository.hasDiff !== true || repository.hasTests !== true) fail(`${runId}: mutation/diff/test evidence incomplete`);
  if (repository.freeAgentCalledTools !== true || !(tools.callCount >= 1) || !(tools.mutationCount >= 1) || tools.writeConfirmed !== true) {
    fail(`${runId}: free single-agent tool mutation evidence incomplete`);
  }
  if (itemExecution.profileId !== execution.profileId) fail(`${runId}: evidence/profile mismatch`);
  if (itemExecution.resolvedTransportClass !== execution.resolvedTransportClass) fail(`${runId}: evidence/transport mismatch`);
  if (itemExecution.maxForegroundAgents !== 1 || itemExecution.maxBackgroundAgents !== 0) fail(`${runId}: serialized agent limits invalid`);
  if (itemExecution.changedFileCount !== repository.changedFileCount) fail(`${runId}: serialized changed-file count mismatch`);
  if (itemExecution.toolCallCount !== tools.callCount || itemExecution.mutationCount !== tools.mutationCount) fail(`${runId}: serialized tool counters mismatch`);
  if (item.draft !== true || item.stateAtVerification !== 'open' || item.readmeVerified !== true) fail(`${runId}: GitHub Draft PR readback incomplete`);
  if (item.closedAfterVerification !== true || item.branchDeletedAfterVerification !== true) fail(`${runId}: cleanup readback incomplete`);
}

console.log(JSON.stringify({
  ok: true,
  sourceRevision: document.sourceRevision,
  verifiedRuns: seenRuns.size,
  invariant: 'browser-request-free-single -> runtime-free-single -> internal-workspace -> mutation/diff/tests -> consent -> verified-draft-pr -> cleanup',
}, null, 2));
