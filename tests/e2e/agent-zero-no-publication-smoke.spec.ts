import { randomBytes, createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from '@playwright/test';

const APP_URL = (process.env.SOVEREIGN_E2E_APP_URL || '').trim();
const BACKEND_URL = (process.env.SOVEREIGN_E2E_BACKEND_PROXY_TARGET || '').trim().replace(/\/$/, '');
const REPO_URL = (process.env.SOVEREIGN_E2E_REPO_URL || '').trim();
const EXPECTED_REVISION = (process.env.SOVEREIGN_E2E_RUNTIME_REVISION || '').trim();
const EXPECTED_BACKEND_DIGEST = (process.env.SOVEREIGN_E2E_BACKEND_DIGEST || '').trim();
const RUN_ID = (process.env.GITHUB_RUN_ID || `local-${Date.now()}`).trim();
const JOB_ID = /^agent-[0-9a-f]{32}$/;
const A2A_REF = /^agent-zero-a2a:(?:retry:)?[A-Za-z0-9._:-]{1,200}$/;
const EMPTY_SHA256 = createHash('sha256').update('').digest('hex');
const TIMEOUT_MS = 900_000;

let accountKey = '';
let accountKeyId = '';
let ephemeralKeyRevoked = false;
let finalEvidence: Record<string, unknown> = {
  schemaVersion: 'sovereign.agent-zero-no-publication-smoke.v1',
  runId: RUN_ID,
  sourceRevision: EXPECTED_REVISION,
  secretValuesReturned: false,
};

test.use({ viewport: { width: 390, height: 844 }, trace: 'off', screenshot: 'off', video: 'off' });
test.setTimeout(TIMEOUT_MS + 180_000);

function requireConfig(): void {
  if (new URL(APP_URL).origin !== 'https://chat.arelorian.de') throw new Error('DEPLOYED_UI_ORIGIN_UNVERIFIED');
  if (new URL(BACKEND_URL).origin !== 'https://sovereign-backend.arelorian.de') throw new Error('CANONICAL_BACKEND_ORIGIN_UNVERIFIED');
  const repo = new URL(REPO_URL);
  if (repo.origin !== 'https://github.com' || repo.pathname.split('/').filter(Boolean).length !== 2) throw new Error('REPOSITORY_URL_UNVERIFIED');
  if (!/^[0-9a-f]{40}$/.test(EXPECTED_REVISION)) throw new Error('EXPECTED_RUNTIME_REVISION_UNVERIFIED');
  if (!/^sha256:[0-9a-f]{64}$/.test(EXPECTED_BACKEND_DIGEST)) throw new Error('EXPECTED_BACKEND_DIGEST_UNVERIFIED');
}

async function provisionAccountKey(): Promise<void> {
  const api = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
  let password = `Sovereign-AgentZero-Smoke-${randomBytes(32).toString('base64url')}!9a`;
  const email = `agent-zero-smoke-${RUN_ID}-${randomBytes(8).toString('hex')}@tests.sovereign.invalid`;
  try {
    const registration = await api.post('/api/auth/register', {
      data: { email, password, displayName: `Agent Zero Smoke ${RUN_ID}` },
    });
    if (registration.status() !== 200) throw new Error(`EPHEMERAL_REGISTRATION_FAILED_${registration.status()}`);
    const user = await registration.json() as { id?: string; isGuest?: boolean; creditStateVerified?: boolean; credits?: number };
    if (!user.id || user.isGuest === true || user.creditStateVerified !== true || Number(user.credits || 0) <= 0) {
      throw new Error('EPHEMERAL_ACCOUNT_EXECUTION_IDENTITY_UNVERIFIED');
    }
    const issued = await api.post('/api/security/account-keys', { data: { label: `Agent Zero No-Publish Smoke ${RUN_ID}` } });
    if (issued.status() !== 201) throw new Error(`ACCOUNT_KEY_ISSUE_FAILED_${issued.status()}`);
    const body = await issued.json() as { id?: string; key?: string };
    accountKeyId = String(body.id || '');
    accountKey = String(body.key || '');
    if (!accountKeyId || !accountKey.startsWith('svk_')) throw new Error('ACCOUNT_KEY_ISSUE_EVIDENCE_INCOMPLETE');
  } finally {
    password = '';
    await api.dispose();
  }
}

async function revokeAccountKey(): Promise<void> {
  if (!accountKeyId || !accountKey) return;
  const api = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
  try {
    const login = await api.post('/api/auth/account-key', { data: { key: accountKey } });
    if (login.status() !== 200) throw new Error(`ACCOUNT_KEY_CLEANUP_LOGIN_FAILED_${login.status()}`);
    const revoked = await api.delete(`/api/security/account-keys/${encodeURIComponent(accountKeyId)}`);
    if (revoked.status() !== 200) throw new Error(`ACCOUNT_KEY_REVOKE_FAILED_${revoked.status()}`);
    ephemeralKeyRevoked = true;
  } finally {
    accountKey = '';
    await api.dispose();
  }
}

async function authenticateDeployedUi(page: Page): Promise<void> {
  await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('sovereign-control-surface-vnext')).toBeVisible({ timeout: 45_000 });
  await page.getByTestId('operator-auth-btn').click();
  const dialog = page.getByRole('dialog', { name: 'Sovereign account session' });
  await expect(dialog).toBeVisible();
  await dialog.locator('#vnext-account-key').fill(accountKey);
  const [login] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/auth/account-key', { timeout: 45_000 }),
    dialog.getByRole('button', { name: 'AUTHENTICATE WITH ACCOUNT KEY' }).click(),
  ]);
  expect(new URL(login.url()).origin).toBe(new URL(BACKEND_URL).origin);
  expect(login.status()).toBe(200);
  await expect(dialog.getByText('AUTHENTICATED', { exact: true })).toBeVisible({ timeout: 45_000 });
  await dialog.getByRole('button', { name: 'Close account session' }).click();
}

function stages(job: any): string[] {
  return Array.isArray(job?.events)
    ? job.events.map((entry: unknown) => typeof entry === 'string' ? entry : JSON.stringify(entry))
    : [];
}

async function getJob(page: Page, jobId: string): Promise<any> {
  const response = await page.request.get(`${BACKEND_URL}/api/user/agent/jobs/${encodeURIComponent(jobId)}`, {
    headers: { 'Cache-Control': 'no-store' },
    maxRedirects: 0,
  });
  if (![200, 503].includes(response.status())) throw new Error(`JOB_READBACK_FAILED_${response.status()}`);
  const body = await response.json().catch(() => null) as any;
  return body?.job || null;
}

async function readFile(page: Page, jobId: string): Promise<any | null> {
  const response = await page.request.post(`${BACKEND_URL}/api/user/agent/jobs/${encodeURIComponent(jobId)}/tools/file`, {
    data: { mode: 'read', path: 'testfile', maxBytes: 16 },
    maxRedirects: 0,
  });
  const body = await response.json().catch(() => null) as any;
  if (body?.tool?.status === 'done') return body.tool;
  return null;
}

async function gitStatus(page: Page, jobId: string): Promise<any> {
  const response = await page.request.post(`${BACKEND_URL}/api/user/agent/jobs/${encodeURIComponent(jobId)}/tools/git-status`, {
    data: {},
    maxRedirects: 0,
  });
  const body = await response.json().catch(() => null) as any;
  if (body?.tool?.status !== 'done') throw new Error(`GIT_STATUS_READBACK_FAILED_${response.status()}`);
  return body.tool;
}

test('deployed Sovereign UI creates exactly one empty testfile through Agent Zero A2A without publication', async ({ page }) => {
  requireConfig();
  await provisionAccountKey();

  const healthResponse = await page.request.get(`${BACKEND_URL}/health`, { headers: { 'Cache-Control': 'no-store' } });
  expect(healthResponse.status()).toBe(200);
  const health = await healthResponse.json() as { status?: string; sourceRevision?: string; imageDigest?: string };
  expect(health.status).toBe('live');
  expect(health.sourceRevision).toBe(EXPECTED_REVISION);
  expect(health.imageDigest).toBe(EXPECTED_BACKEND_DIGEST);

  const browserPosts: Array<{ origin: string; path: string; body: unknown }> = [];
  page.on('request', request => {
    if (request.method() !== 'POST') return;
    const url = new URL(request.url());
    let body: unknown = null;
    try { body = request.postDataJSON(); } catch { body = null; }
    browserPosts.push({ origin: url.origin, path: url.pathname, body });
  });

  await authenticateDeployedUi(page);

  const mission = [
    `Repository: ${REPO_URL}`,
    'Erstelle im Root des bereitgestellten Repository-Workspaces genau eine leere reguläre Datei testfile.',
    'Verändere keine andere Datei. Erzeuge keinen Commit und keinen Pull Request.',
    'Melde nach Fertigstellung den Abschluss des Auftrages.',
  ].join('\n');

  const composer = page.getByTestId('mission__textarea');
  await expect(composer).toBeVisible();
  await composer.fill(mission);
  await expect(page.getByTestId('agent-mode-single')).toHaveAttribute('aria-pressed', 'true');

  const [startResponse] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/user/agent/repository/run', { timeout: 120_000 }),
    page.getByTestId('builder__start-task').click(),
  ]);
  expect(new URL(startResponse.url()).origin).toBe(new URL(BACKEND_URL).origin);
  expect(startResponse.status()).toBe(202);
  const startRequest = startResponse.request().postDataJSON() as Record<string, unknown>;
  expect(startRequest).toMatchObject({
    mode: 'free',
    agentMode: 'single',
    intentMode: 'repository_execution',
    repositoryUrl: REPO_URL,
    repositoryBranch: 'main',
  });
  expect(startRequest).not.toHaveProperty('githubAccessToken');

  const startBody = await startResponse.json() as any;
  const jobId = String(startBody?.jobId || '');
  const workspaceId = String(startBody?.job?.workspaceId || '');
  expect(jobId).toMatch(JOB_ID);
  expect(workspaceId).toBeTruthy();

  const deadline = Date.now() + TIMEOUT_MS;
  let fileTool: any | null = null;
  let job: any = null;
  while (Date.now() < deadline) {
    job = await getJob(page, jobId);
    fileTool = await readFile(page, jobId);
    if (fileTool?.metadata?.bytes === 0) break;
    await page.waitForTimeout(2_000);
  }
  if (!fileTool) throw new Error('TESTFILE_READBACK_TIMEOUT');
  expect(fileTool.metadata.path).toBe('testfile');
  expect(fileTool.metadata.bytes).toBe(0);
  expect(fileTool.metadata.sha256).toBe(EMPTY_SHA256);

  const statusTool = await gitStatus(page, jobId);
  const gitFiles = Array.isArray(statusTool?.metadata?.files) ? statusTool.metadata.files.map(String) : [];
  expect(statusTool.metadata.changed_files).toBe(1);
  expect(gitFiles).toEqual(['?? testfile']);

  job = await getJob(page, jobId);
  const eventText = stages(job);
  const countStage = (needle: string) => eventText.filter(item => item.includes(needle)).length;
  expect(countStage('agent_zero_repository_access_delegated')).toBe(1);
  expect(countStage('agent_zero_a2a_submit_queued')).toBe(1);
  expect(countStage('agent_zero_a2a_submitted')).toBe(1);
  expect(countStage('agent_zero_a2a_retry_submitted')).toBe(0);
  expect(countStage('agent_zero_a2a_original_task_lost')).toBe(0);
  expect(String(job?.draftPrUrl || '')).toBe('');
  expect(String(job?.prUrl || '')).toBe('');

  const forbiddenBrowserPosts = browserPosts.filter(({ path }) => (
    path === '/api/user/agent/swarm/run'
    || path === '/api/user/agent/jobs'
    || path === '/api/user/agent/toolchain/handoff'
    || path.includes('/draft-pr/create')
    || path.includes('/auth/github')
  ));
  expect(forbiddenBrowserPosts).toEqual([]);

  const executionPosts = browserPosts.filter(({ path }) => path === '/api/user/agent/repository/run');
  expect(executionPosts).toHaveLength(1);
  expect(executionPosts[0]?.body).not.toHaveProperty('githubAccessToken');

  finalEvidence = {
    schemaVersion: 'sovereign.agent-zero-no-publication-smoke.v1',
    ok: true,
    status: 'VERIFIED',
    runId: RUN_ID,
    sourceRevision: EXPECTED_REVISION,
    backendDigest: EXPECTED_BACKEND_DIGEST,
    uiOrigin: new URL(APP_URL).origin,
    backendOrigin: new URL(BACKEND_URL).origin,
    jobId,
    workspaceId,
    repositoryUrl: REPO_URL,
    executionRequest: {
      mode: startRequest.mode,
      agentMode: startRequest.agentMode,
      intentMode: startRequest.intentMode,
      repositoryBranch: startRequest.repositoryBranch,
      githubAccessTokenPresent: Object.prototype.hasOwnProperty.call(startRequest, 'githubAccessToken'),
    },
    a2a: {
      repositoryAccessDelegatedEvents: countStage('agent_zero_repository_access_delegated'),
      queuedEvents: countStage('agent_zero_a2a_submit_queued'),
      submittedEvents: countStage('agent_zero_a2a_submitted'),
      retrySubmittedEvents: countStage('agent_zero_a2a_retry_submitted'),
      originalTaskLostEvents: countStage('agent_zero_a2a_original_task_lost'),
      externalRef: String(job?.externalRef || ''),
    },
    fileReadback: {
      path: 'testfile',
      regularFileVerifiedByFileTool: true,
      bytes: fileTool.metadata.bytes,
      sha256: fileTool.metadata.sha256,
    },
    gitStatus: {
      changedFileCount: statusTool.metadata.changed_files,
      files: gitFiles,
      provesNoCommitOfTestfile: gitFiles.includes('?? testfile'),
    },
    publication: {
      draftPrUrl: job?.draftPrUrl || null,
      prUrl: job?.prUrl || null,
      draftPrCreateBrowserPosts: browserPosts.filter(({ path }) => path.includes('/draft-pr/create')).length,
    },
    forbiddenBrowserPosts,
    secretValuesReturned: false,
  };
});

test.afterAll(async () => {
  let cleanupError: Error | null = null;
  try { await revokeAccountKey(); } catch (error) { cleanupError = error instanceof Error ? error : new Error(String(error)); }
  await mkdir('test-results', { recursive: true });
  await writeFile('test-results/agent-zero-no-publication-evidence.json', `${JSON.stringify({
    ...finalEvidence,
    identity: {
      ephemeralAccountKeyIssued: Boolean(accountKeyId),
      ephemeralAccountKeyRevoked: accountKeyId ? ephemeralKeyRevoked : null,
      protectedValuePersistedInEvidence: false,
    },
  }, null, 2)}\n`, 'utf8');
  if (cleanupError) throw cleanupError;
});
