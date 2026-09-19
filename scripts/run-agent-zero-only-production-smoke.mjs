import { createHash, randomBytes } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium, request as playwrightRequest } from '@playwright/test';

const APP_URL = (process.env.SOVEREIGN_E2E_APP_URL || 'https://chat.arelorian.de').replace(/\/+$/, '');
const BACKEND_URL = (process.env.SOVEREIGN_E2E_BACKEND_URL || 'https://sovereign-backend.arelorian.de').replace(/\/+$/, '');
const REPO_URL = (process.env.SOVEREIGN_E2E_REPO_URL || 'https://github.com/OuroborosCollective/Sovereign-Studio-ato').replace(/\.git$/i, '');
const EXPECTED_REVISION = String(process.env.SOVEREIGN_E2E_EXPECTED_REVISION || '').trim().toLowerCase();
const EXPECTED_IMAGE_DIGEST = String(process.env.SOVEREIGN_E2E_EXPECTED_IMAGE_DIGEST || '').trim().toLowerCase();
const CONFIGURED_ACCOUNT_KEY = String(process.env.SOVEREIGN_E2E_ACCOUNT_KEY || '').trim();
const RUN_ID = String(process.env.GITHUB_RUN_ID || `local-${Date.now()}`).replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 80);
const EVIDENCE_PATH = 'test-results/agent-zero-only-production-smoke.json';
const EMPTY_SHA256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
const JOB_ID_RE = /^agent-[0-9a-f]{32}$/;
const FINAL_A2A_REF_RE = /^agent-zero-a2a:(?!pending:|claim:|retry:)[A-Za-z0-9._:-]{1,200}$/;
const POLL_TIMEOUT_MS = Math.max(240_000, Math.min(Number.parseInt(process.env.SOVEREIGN_E2E_REPOSITORY_READY_TIMEOUT_MS || '900000', 10) || 900_000, 1_200_000));
const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

const smokeInstruction = [
  `Repository: ${REPO_URL}`,
  'Erstelle im Root des bereitgestellten Repository-Workspaces genau eine leere reguläre Datei testfile. Verändere keine andere Datei. Erzeuge keinen Commit und keinen Pull Request. Melde nach Fertigstellung den Abschluss des Auftrages.',
].join('\n');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function record(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function stringValue(value) {
  return typeof value === 'string' ? value : '';
}

function eventStages(job) {
  return Array.isArray(job.events)
    ? job.events.map((event) => stringValue(record(event).stage)).filter(Boolean)
    : [];
}

function countStage(stages, name) {
  return stages.filter((stage) => stage === name).length;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function safeUrl(url) {
  const parsed = new URL(url);
  return { origin: parsed.origin, path: parsed.pathname };
}

function assertConfiguration() {
  assert(/^https:\/\//.test(APP_URL), 'DEPLOYED_UI_HTTPS_REQUIRED');
  assert(/^https:\/\//.test(BACKEND_URL), 'PRODUCTION_BACKEND_HTTPS_REQUIRED');
  assert(/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(REPO_URL), 'EXACT_GITHUB_REPOSITORY_URL_REQUIRED');
  assert(/^[0-9a-f]{40}$/.test(EXPECTED_REVISION), 'EXPECTED_REVISION_REQUIRED');
  assert(/^sha256:[0-9a-f]{64}$/.test(EXPECTED_IMAGE_DIGEST), 'EXPECTED_IMAGE_DIGEST_REQUIRED');
}

async function readBackendIdentity() {
  const api = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
  try {
    const response = await api.get('/health', { headers: { 'Cache-Control': 'no-store' } });
    assert(response.status() === 200, `BACKEND_HEALTH_HTTP_${response.status()}`);
    const body = record(await response.json().catch(() => null));
    assert(body.ok === true && body.status === 'live', 'BACKEND_HEALTH_NOT_LIVE');
    assert(body.sourceRevision === EXPECTED_REVISION, 'BACKEND_REVISION_MISMATCH');
    assert(body.imageDigest === EXPECTED_IMAGE_DIGEST, 'BACKEND_IMAGE_DIGEST_MISMATCH');
    return {
      httpStatus: response.status(),
      sourceRevision: body.sourceRevision,
      imageDigest: body.imageDigest,
      verified: true,
    };
  } finally {
    await api.dispose();
  }
}

async function provisionAccountKey() {
  if (CONFIGURED_ACCOUNT_KEY) {
    return {
      key: CONFIGURED_ACCOUNT_KEY,
      keyId: '',
      accountId: '',
      source: 'protected_repository_secret',
      ephemeral: false,
    };
  }

  const api = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
  let password = `Sovereign-AgentZero-Smoke-${randomBytes(24).toString('base64url')}!9a`;
  try {
    const email = `agent-zero-only-${RUN_ID}-${randomBytes(6).toString('hex')}@tests.sovereign.invalid`;
    const registration = await api.post('/api/auth/register', {
      data: { email, password, displayName: `Agent Zero Only Smoke ${RUN_ID}` },
    });
    assert(registration.status() === 200, `EPHEMERAL_REGISTRATION_HTTP_${registration.status()}`);
    const user = record(await registration.json().catch(() => null));
    assert(typeof user.id === 'string' && user.id.length > 0, 'EPHEMERAL_ACCOUNT_ID_MISSING');
    assert(user.isGuest !== true, 'EPHEMERAL_ACCOUNT_MUST_NOT_BE_GUEST');
    assert(user.creditStateVerified === true, 'EPHEMERAL_ACCOUNT_CREDIT_STATE_UNVERIFIED');

    const issued = await api.post('/api/security/account-keys', {
      data: { label: `Agent Zero only production smoke ${RUN_ID}` },
    });
    assert(issued.status() === 201, `EPHEMERAL_ACCOUNT_KEY_HTTP_${issued.status()}`);
    const issuedBody = record(await issued.json().catch(() => null));
    const key = stringValue(issuedBody.key).trim();
    const keyId = stringValue(issuedBody.id).trim();
    assert(key.startsWith('svk_') && keyId, 'EPHEMERAL_ACCOUNT_KEY_INVALID');
    return {
      key,
      keyId,
      accountId: stringValue(user.id),
      source: 'ephemeral_product_registration',
      ephemeral: true,
    };
  } finally {
    password = '';
    await api.dispose();
  }
}

async function revokeEphemeralAccountKey(identity) {
  if (!identity.ephemeral || !identity.keyId || !identity.key) return false;
  const api = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
  try {
    const login = await api.post('/api/auth/account-key', { data: { key: identity.key } });
    if (login.status() !== 200) return false;
    const revoked = await api.delete(`/api/security/account-keys/${encodeURIComponent(identity.keyId)}`);
    return revoked.status() === 200;
  } finally {
    await api.dispose();
  }
}

async function authenticateDeployedUi(page, identity) {
  const navigation = await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  assert(navigation && navigation.status() < 400, `DEPLOYED_UI_HTTP_${navigation?.status() ?? 0}`);
  await page.getByTestId('sovereign-control-surface-vnext').waitFor({ state: 'visible', timeout: 45_000 });
  await page.getByTestId('operator-auth-btn').click();

  const dialog = page.getByRole('dialog', { name: 'Sovereign account session' });
  await dialog.waitFor({ state: 'visible', timeout: 30_000 });
  const accountKey = dialog.locator('#vnext-account-key');
  await accountKey.fill(identity.key);

  const authenticate = dialog.getByRole('button', { name: 'AUTHENTICATE WITH ACCOUNT KEY' });
  const [loginResponse] = await Promise.all([
    page.waitForResponse((response) => {
      try {
        return response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/auth/account-key';
      } catch {
        return false;
      }
    }, { timeout: 45_000 }),
    authenticate.click(),
  ]);
  assert(loginResponse.status() === 200, `DEPLOYED_UI_AUTH_HTTP_${loginResponse.status()}`);
  const loginBody = record(await loginResponse.json().catch(() => null));
  const accountId = stringValue(loginBody.id).trim();
  assert(accountId, 'DEPLOYED_UI_AUTH_ACCOUNT_ID_MISSING');
  if (identity.accountId) assert(accountId === identity.accountId, 'DEPLOYED_UI_AUTH_ACCOUNT_MISMATCH');

  const authOrigin = new URL(loginResponse.url()).origin;
  assert(
    authOrigin === new URL(APP_URL).origin || authOrigin === new URL(BACKEND_URL).origin,
    'DEPLOYED_UI_AUTH_ORIGIN_UNEXPECTED',
  );

  const me = await page.request.get(new URL('/api/auth/me', loginResponse.url()).href, {
    headers: { 'Cache-Control': 'no-store' },
    maxRedirects: 0,
  });
  assert(me.status() === 200, `DEPLOYED_UI_SESSION_HTTP_${me.status()}`);
  const session = record(await me.json().catch(() => null));
  assert(session.id === accountId, 'DEPLOYED_UI_SESSION_ACCOUNT_MISMATCH');
  assert(session.isGuest === false, 'DEPLOYED_UI_SESSION_MUST_NOT_BE_GUEST');
  assert(session.creditStateVerified === true, 'DEPLOYED_UI_SESSION_CREDIT_STATE_UNVERIFIED');

  await dialog.getByText('AUTHENTICATED', { exact: true }).waitFor({ state: 'visible', timeout: 30_000 });
  await dialog.getByRole('button', { name: 'Close account session' }).click();

  return {
    httpStatus: navigation.status(),
    origin: new URL(page.url()).origin,
    authOrigin,
    accountIdentitySha256: sha256(accountId),
  };
}

function forbiddenMutationReason(observation) {
  const path = observation.path;
  const host = new URL(observation.origin).hostname;
  if (path === '/api/user/agent/swarm/run') return 'SWARM_EXECUTION_ROUTE_USED';
  if (path === '/api/user/agent/jobs' && observation.method === 'POST') return 'GENERIC_JOB_EXECUTION_ROUTE_USED';
  if (path.includes('/toolchain/handoff')) return 'TOOLCHAIN_HANDOFF_EXECUTION_ROUTE_USED';
  if (path.startsWith('/api/billing/') || path.includes('/credits/')) return 'BILLING_OR_CREDITS_EXECUTION_ROUTE_USED';
  if (/draft[-_/]?pr|publish/i.test(path)) return 'DRAFT_PR_PUBLICATION_ROUTE_USED';
  if (/coding[-_/]?agent|jules/i.test(path)) return 'GITHUB_CODING_AGENT_ROUTE_USED';
  if ((host === 'github.com' || host === 'api.github.com') && MUTATING_METHODS.has(observation.method)) {
    return 'DIRECT_GITHUB_MUTATION_USED';
  }
  return null;
}

async function startRepositoryMission(page, browserMutations) {
  const composer = page.getByTestId('mission__textarea');
  await composer.waitFor({ state: 'visible', timeout: 30_000 });
  await composer.fill(smokeInstruction);
  const single = page.getByTestId('agent-mode-single');
  await single.waitFor({ state: 'visible', timeout: 30_000 });
  assert((await single.getAttribute('aria-pressed')) === 'true', 'DEPLOYED_UI_SINGLE_AGENT_NOT_ACTIVE');

  const startPromise = page.waitForResponse((response) => {
    try {
      return response.request().method() === 'POST'
        && new URL(response.url()).pathname === '/api/user/agent/repository/run';
    } catch {
      return false;
    }
  }, { timeout: 180_000 });

  const startButton = page.getByTestId('builder__start-task');
  await startButton.click();
  const startResponse = await startPromise;
  const startRequest = startResponse.request();
  const requestBody = record(startRequest.postDataJSON());

  assert(startResponse.status() === 202, `REPOSITORY_START_HTTP_${startResponse.status()}`);
  assert(!Object.prototype.hasOwnProperty.call(requestBody, 'githubAccessToken'), 'GITHUB_CREDENTIAL_PRESENT_ON_EXECUTION_REQUEST');
  assert(!Object.prototype.hasOwnProperty.call(requestBody, 'githubToken'), 'GITHUB_TOKEN_PRESENT_ON_EXECUTION_REQUEST');
  assert(requestBody.mode === 'free', 'REPOSITORY_EXECUTION_MODE_NOT_FREE');
  assert(requestBody.agentMode === 'single', 'REPOSITORY_EXECUTION_NOT_SINGLE_AGENT');
  assert(requestBody.intentMode === 'repository_execution', 'REPOSITORY_EXECUTION_INTENT_INVALID');
  assert(requestBody.repositoryUrl === REPO_URL, 'REPOSITORY_EXECUTION_TARGET_MISMATCH');
  assert(requestBody.repositoryBranch === 'main', 'REPOSITORY_EXECUTION_BRANCH_MISMATCH');
  assert(requestBody.cloneRepo !== true, 'SOVEREIGN_CLONE_REQUEST_FORBIDDEN');
  assert(!Array.isArray(requestBody.stagedFiles) || requestBody.stagedFiles.length === 0, 'STAGED_FILE_FALLBACK_FORBIDDEN');

  const startBody = record(await startResponse.json().catch(() => null));
  const job = record(startBody.job);
  const jobId = stringValue(startBody.jobId || job.jobId).trim();
  const workspaceId = stringValue(job.workspaceId).trim();
  assert(startBody.execution === 'repository-single-a2a', 'REPOSITORY_EXECUTION_RUNTIME_MISMATCH');
  assert(JOB_ID_RE.test(jobId), 'PERSISTED_REPOSITORY_JOB_ID_INVALID');
  assert(workspaceId, 'PERSISTED_REPOSITORY_WORKSPACE_ID_MISSING');

  const requestUrl = safeUrl(startResponse.url());
  browserMutations.push({
    method: 'POST',
    origin: requestUrl.origin,
    path: requestUrl.path,
    source: 'observed-repository-start',
  });

  return {
    jobId,
    workspaceId,
    apiOrigin: requestUrl.origin,
    initialExternalRef: stringValue(job.externalRef),
    requestEvidence: {
      route: requestUrl.path,
      mode: requestBody.mode,
      agentMode: requestBody.agentMode,
      intentMode: requestBody.intentMode,
      repositoryUrl: requestBody.repositoryUrl,
      repositoryBranch: requestBody.repositoryBranch,
      githubAccessTokenPresent: Object.prototype.hasOwnProperty.call(requestBody, 'githubAccessToken'),
      cloneRepoRequested: requestBody.cloneRepo === true,
      stagedFilesPresent: Array.isArray(requestBody.stagedFiles) && requestBody.stagedFiles.length > 0,
      missionSha256: sha256(stringValue(requestBody.mission)),
    },
  };
}

async function readJob(page, apiOrigin, jobId) {
  const response = await page.request.get(
    `${apiOrigin}/api/user/agent/jobs/${encodeURIComponent(jobId)}`,
    { headers: { 'Cache-Control': 'no-store' }, maxRedirects: 0 },
  );
  if (response.status() === 503) return { transient: true, status: 503, job: null };
  assert(response.status() === 200, `REPOSITORY_JOB_READBACK_HTTP_${response.status()}`);
  const body = record(await response.json().catch(() => null));
  return { transient: false, status: response.status(), job: record(body.job) };
}

async function waitForRepositoryEvidence(page, apiOrigin, jobId, workspaceId) {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let lastJob = null;
  while (Date.now() < deadline) {
    const observed = await readJob(page, apiOrigin, jobId);
    if (observed.transient) {
      await sleep(1_500);
      continue;
    }
    const job = observed.job;
    lastJob = job;
    assert(job.jobId === jobId, 'REPOSITORY_JOB_ID_DRIFT');
    assert(job.workspaceId === workspaceId, 'REPOSITORY_WORKSPACE_ID_DRIFT');
    assert(sha256(stringValue(job.mission)) === sha256(smokeInstruction), 'REPOSITORY_JOB_MISSION_IDENTITY_DRIFT');

    const stages = eventStages(job);
    const failedA2AStage = stages.find((stage) => [
      'agent_zero_a2a_submit_failed',
      'agent_zero_a2a_submit_outcome_unknown',
      'agent_zero_a2a_task_failed',
      'agent_zero_a2a_task_interrupted',
      'agent_zero_a2a_task_stalled',
      'agent_zero_a2a_retry_task_lost',
    ].includes(stage));
    assert(!failedA2AStage, `AGENT_ZERO_A2A_FAILURE_${failedA2AStage || 'UNKNOWN'}`);
    assert(countStage(stages, 'agent_zero_a2a_retry_submitted') === 0, 'AGENT_ZERO_A2A_RETRY_FORBIDDEN_IN_SMOKE');

    const ready = stages.includes('repository_ready_for_draft_pr') && job.prState === 'ready';
    if (ready) return job;

    if (job.status === 'blocked' || job.status === 'failed') {
      throw new Error(`REPOSITORY_JOB_TERMINAL_BEFORE_EVIDENCE_READY_${stringValue(job.blocker) || job.status}`);
    }
    await sleep(1_500);
  }

  throw new Error(`REPOSITORY_JOB_EVIDENCE_TIMEOUT_${stringValue(lastJob?.status) || 'unknown'}`);
}

async function readTestfile(page, apiOrigin, jobId) {
  const response = await page.request.post(
    `${apiOrigin}/api/user/agent/jobs/${encodeURIComponent(jobId)}/tools/file`,
    { data: { mode: 'read', path: 'testfile', maxBytes: 1 }, maxRedirects: 0 },
  );
  const body = record(await response.json().catch(() => null));
  const tool = record(body.tool);
  const metadata = record(tool.metadata);
  assert(tool.status === 'done', `TESTFILE_READBACK_NOT_DONE_HTTP_${response.status()}`);
  assert(metadata.path === 'testfile', 'TESTFILE_READBACK_PATH_MISMATCH');
  assert(metadata.bytes === 0, 'TESTFILE_NOT_EMPTY');
  assert(metadata.sha256 === EMPTY_SHA256, 'TESTFILE_EMPTY_SHA256_MISMATCH');
  assert(stringValue(tool.output) === '', 'TESTFILE_OUTPUT_NOT_EMPTY');
  return {
    route: `/api/user/agent/jobs/${jobId}/tools/file`,
    toolStatus: tool.status,
    regularFileVerified: true,
    path: metadata.path,
    bytes: metadata.bytes,
    sha256: metadata.sha256,
  };
}

async function readGitStatus(page, apiOrigin, jobId) {
  const response = await page.request.post(
    `${apiOrigin}/api/user/agent/jobs/${encodeURIComponent(jobId)}/tools/git-status`,
    { data: {}, maxRedirects: 0 },
  );
  const body = record(await response.json().catch(() => null));
  const tool = record(body.tool);
  assert(tool.status === 'done', `GIT_STATUS_READBACK_NOT_DONE_HTTP_${response.status()}`);
  const changedFiles = Array.isArray(tool.changedFiles) ? tool.changedFiles.map(String) : [];
  assert(changedFiles.length === 1 && changedFiles[0] === 'testfile', 'GIT_STATUS_NOT_EXACTLY_TESTFILE');
  const output = stringValue(tool.output || tool.stdout);
  assert(/(?:^|\n)\?\?\s+testfile(?:\n|$)/.test(output), 'TESTFILE_NOT_UNTRACKED_WORKTREE_EVIDENCE');
  return {
    route: `/api/user/agent/jobs/${jobId}/tools/git-status`,
    toolStatus: tool.status,
    changedFiles,
    untrackedTestfileVerified: true,
  };
}

async function main() {
  assertConfiguration();
  await mkdir('test-results', { recursive: true });

  const evidence = {
    schemaVersion: 'sovereign.agent-zero-only-production-smoke.v1',
    runId: RUN_ID,
    status: 'RUNNING',
    checkedAt: new Date().toISOString(),
    expected: {
      revision: EXPECTED_REVISION,
      imageDigest: EXPECTED_IMAGE_DIGEST,
      repositoryUrl: REPO_URL,
      missionSha256: sha256(smokeInstruction),
    },
    backend: null,
    frontend: null,
    request: null,
    job: null,
    fileReadback: null,
    gitStatusReadback: null,
    negativeEvidence: null,
    cleanup: { ephemeralAccountKeyRevoked: null },
  };

  let browser;
  let identity = null;
  try {
    evidence.backend = await readBackendIdentity();
    identity = await provisionAccountKey();

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();

    const browserMutations = [];
    let observeMissionMutations = false;
    page.on('request', (request) => {
      if (!observeMissionMutations || !MUTATING_METHODS.has(request.method())) return;
      try {
        const observed = safeUrl(request.url());
        browserMutations.push({
          method: request.method(),
          origin: observed.origin,
          path: observed.path,
          source: 'deployed-ui',
        });
      } catch {
        // Unparseable requests are not promoted into evidence.
      }
    });

    evidence.frontend = await authenticateDeployedUi(page, identity);
    observeMissionMutations = true;
    const started = await startRepositoryMission(page, browserMutations);
    evidence.request = started.requestEvidence;

    const finalJob = await waitForRepositoryEvidence(page, started.apiOrigin, started.jobId, started.workspaceId);
    const stages = eventStages(finalJob);
    const finalRef = stringValue(finalJob.externalRef);
    const changedFiles = Array.isArray(finalJob.changedFiles) ? finalJob.changedFiles.map(String) : [];

    assert(countStage(stages, 'agent_zero_repository_access_delegated') === 1, 'AGENT_ZERO_REPOSITORY_DELEGATION_EVENT_COUNT_INVALID');
    assert(countStage(stages, 'agent_zero_a2a_submit_queued') === 1, 'AGENT_ZERO_A2A_QUEUE_EVENT_COUNT_INVALID');
    assert(countStage(stages, 'agent_zero_a2a_submitted') === 1, 'AGENT_ZERO_A2A_SUBMISSION_COUNT_NOT_EXACTLY_ONE');
    assert(countStage(stages, 'agent_zero_a2a_retry_submitted') === 0, 'AGENT_ZERO_A2A_RETRY_PRESENT');
    assert(FINAL_A2A_REF_RE.test(finalRef), 'FINAL_AGENT_ZERO_A2A_BINDING_NOT_SINGLE_OR_STABLE');
    assert(!stages.includes('repo_clone_completed'), 'SOVEREIGN_REPOSITORY_CLONE_EVENT_FORBIDDEN');
    assert(changedFiles.length === 1 && changedFiles[0] === 'testfile', 'JOB_CHANGED_FILES_NOT_EXACTLY_TESTFILE');
    assert(typeof finalJob.diffSummary === 'string' && finalJob.diffSummary.includes('testfile'), 'TESTFILE_DIFF_EVIDENCE_MISSING');
    assert(typeof finalJob.testSummary === 'string' && finalJob.testSummary.trim().length > 0, 'SOVEREIGN_REGRESSION_EVIDENCE_MISSING');
    assert(!finalJob.draftPrUrl && !finalJob.prUrl, 'DRAFT_PR_PUBLICATION_ALREADY_OCCURRED');

    evidence.fileReadback = await readTestfile(page, started.apiOrigin, started.jobId);
    evidence.gitStatusReadback = await readGitStatus(page, started.apiOrigin, started.jobId);

    observeMissionMutations = false;
    const uniqueMutations = browserMutations.filter((entry, index, all) =>
      all.findIndex((candidate) =>
        candidate.method === entry.method
        && candidate.origin === entry.origin
        && candidate.path === entry.path
        && candidate.source === entry.source
      ) === index
    );
    const forbidden = uniqueMutations
      .map((entry) => ({ ...entry, reason: forbiddenMutationReason(entry) }))
      .filter((entry) => entry.reason);
    assert(forbidden.length === 0, `FORBIDDEN_EXECUTION_SIDE_PATH_${forbidden.map((entry) => entry.reason).join(',')}`);

    const eventSidePath = stages.find((stage) => /swarm|billing|credit|coding_agent|jules|draft_pr_created|draft_pr_published/i.test(stage));
    assert(!eventSidePath, `FORBIDDEN_JOB_EVENT_SIDE_PATH_${eventSidePath || 'UNKNOWN'}`);

    evidence.job = {
      jobId: started.jobId,
      workspaceId: started.workspaceId,
      status: finalJob.status,
      prState: finalJob.prState,
      externalRef: finalRef,
      changedFiles,
      missionSha256: sha256(stringValue(finalJob.mission)),
      eventStages: stages,
      exactOneAgentZeroA2ATask: countStage(stages, 'agent_zero_a2a_submitted') === 1
        && countStage(stages, 'agent_zero_a2a_retry_submitted') === 0,
      regressionEvidencePresent: typeof finalJob.testSummary === 'string' && finalJob.testSummary.trim().length > 0,
      diffEvidencePresent: typeof finalJob.diffSummary === 'string' && finalJob.diffSummary.includes('testfile'),
      draftPrPublished: Boolean(finalJob.draftPrUrl || finalJob.prUrl),
    };
    evidence.negativeEvidence = {
      githubCredentialOnExecutionRequest: evidence.request.githubAccessTokenPresent,
      sovereignCloneRequested: evidence.request.cloneRepoRequested,
      stagedFileFallbackRequested: evidence.request.stagedFilesPresent,
      swarmExecutionObserved: uniqueMutations.some((entry) => entry.path === '/api/user/agent/swarm/run'),
      genericJobExecutionObserved: uniqueMutations.some((entry) => entry.path === '/api/user/agent/jobs' && entry.method === 'POST'),
      billingOrCreditsExecutionObserved: uniqueMutations.some((entry) => entry.path.startsWith('/api/billing/') || entry.path.includes('/credits/')),
      toolchainHandoffObserved: uniqueMutations.some((entry) => entry.path.includes('/toolchain/handoff')),
      githubCodingAgentObserved: uniqueMutations.some((entry) => /coding[-_/]?agent|jules/i.test(entry.path))
        || stages.some((stage) => /coding_agent|jules/i.test(stage)),
      draftPrPublicationObserved: Boolean(finalJob.draftPrUrl || finalJob.prUrl)
        || uniqueMutations.some((entry) => /draft[-_/]?pr|publish/i.test(entry.path)),
      directGitHubMutationObserved: uniqueMutations.some((entry) => {
        const host = new URL(entry.origin).hostname;
        return (host === 'github.com' || host === 'api.github.com') && MUTATING_METHODS.has(entry.method);
      }),
      oldJobReused: false,
      commitCreated: !evidence.gitStatusReadback.untrackedTestfileVerified,
      observedMutationRoutes: uniqueMutations.map(({ method, origin, path, source }) => ({ method, origin, path, source })),
    };

    assert(Object.values({
      githubCredentialOnExecutionRequest: evidence.negativeEvidence.githubCredentialOnExecutionRequest,
      sovereignCloneRequested: evidence.negativeEvidence.sovereignCloneRequested,
      stagedFileFallbackRequested: evidence.negativeEvidence.stagedFileFallbackRequested,
      swarmExecutionObserved: evidence.negativeEvidence.swarmExecutionObserved,
      genericJobExecutionObserved: evidence.negativeEvidence.genericJobExecutionObserved,
      billingOrCreditsExecutionObserved: evidence.negativeEvidence.billingOrCreditsExecutionObserved,
      toolchainHandoffObserved: evidence.negativeEvidence.toolchainHandoffObserved,
      githubCodingAgentObserved: evidence.negativeEvidence.githubCodingAgentObserved,
      draftPrPublicationObserved: evidence.negativeEvidence.draftPrPublicationObserved,
      directGitHubMutationObserved: evidence.negativeEvidence.directGitHubMutationObserved,
      oldJobReused: evidence.negativeEvidence.oldJobReused,
      commitCreated: evidence.negativeEvidence.commitCreated,
    }).every((value) => value === false), 'NEGATIVE_EXECUTION_EVIDENCE_NOT_CLEAN');

    evidence.status = 'VERIFIED';
    evidence.checkedAt = new Date().toISOString();
    await context.close();
  } catch (error) {
    evidence.status = 'FAILED';
    evidence.checkedAt = new Date().toISOString();
    evidence.failure = {
      name: error instanceof Error ? error.name : 'Error',
      message: String(error instanceof Error ? error.message : error).slice(0, 500),
    };
    throw error;
  } finally {
    if (browser) await browser.close().catch(() => undefined);
    if (identity) {
      const revoked = await revokeEphemeralAccountKey(identity).catch(() => false);
      evidence.cleanup.ephemeralAccountKeyRevoked = identity.ephemeral ? revoked : null;
      identity.key = '';
    }
    await writeFile(EVIDENCE_PATH, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
    console.log(`AGENT_ZERO_ONLY_PRODUCTION_SMOKE_${evidence.status} evidence=${EVIDENCE_PATH}`);
  }
}

await main();
