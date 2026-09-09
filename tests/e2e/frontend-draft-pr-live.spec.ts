import { mkdir, writeFile } from 'node:fs/promises';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { validateGitHubTokenFormat } from '../../src/features/product/runtime/githubAccessRuntime';

const LIVE_ENABLED = process.env.SOVEREIGN_E2E_LIVE === '1';
const ACCOUNT_KEY = process.env.SOVEREIGN_E2E_ACCOUNT_KEY?.trim() || '';
const GITHUB_TOKEN = process.env.SOVEREIGN_E2E_GITHUB_TOKEN?.trim() || '';
const REPO_URL = process.env.SOVEREIGN_E2E_REPO_URL?.trim() || '';
const APP_URL = process.env.SOVEREIGN_E2E_APP_URL?.trim() || 'https://127.0.0.1:3000';
const RUN_ID = process.env.GITHUB_RUN_ID?.trim() || `local-${Date.now()}`;
const MARKER = `SOVEREIGN_FRONTEND_DRAFT_PR_CANARY:${RUN_ID}`;
const CANARY_PATH = `docs/runtime-canary/frontend-draft-pr-${RUN_ID}.md`;

interface PullReadback {
  number: number;
  html_url: string;
  state: string;
  draft: boolean;
  merged_at: string | null;
  head: { ref: string; sha: string };
  base: { ref: string };
}
interface JobReadback {
  jobId?: string;
  id?: string;
  status?: string;
  lastError?: string;
  blocker?: string;
}
interface Evidence {
  runId: string;
  marker: string;
  path: string;
  authMode: 'account-key' | 'guest';
  jobId: string;
  prNumber: number;
  prUrl: string;
  headRef: string;
  headSha: string;
  baseRef: string;
  stateAtVerification: string;
  draftVerified: boolean;
  canaryFileVerified: boolean;
  markerVerified: boolean;
  closedAfterVerification: boolean;
  branchDeletedAfterVerification: boolean;
}
let evidence: Evidence | null = null;
let linkedJobId = '';
let createdPrNumber = 0;
let backendPublishedHead = '';
let phase = 'configuration';
const observations: { phase: string; at: string }[] = [];
function reached(next: string): void {
  phase = next;
  observations.push({ phase, at: new Date().toISOString() });
  console.log('CANARY_PHASE', phase);
}
function redactDiagnostic(value: unknown): string {
  let text = String(value);
  for (const secret of [ACCOUNT_KEY, GITHUB_TOKEN]) {
    if (secret) text = text.split(secret).join('[redacted]');
  }
  return text.replace(/\bghs_[A-Za-z0-9._-]+/g, '[redacted]')
    .replace(/\b(?:gh[pour]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)\b/g, '[redacted]')
    .replace(/(Bearer\s+)\S+/gi, '$1[redacted]').slice(0, 1500);
}
function coordinates(): { owner: string; repo: string } {
  const parsed = new URL(REPO_URL);
  const parts = parsed.pathname.split('/').filter(Boolean);
  if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || parts.length !== 2) {
    throw new Error('Live canary requires exactly one HTTPS GitHub repository.');
  }
  return { owner: parts[0], repo: parts[1].replace(/\.git$/i, '') };
}
async function githubJson<T>(request: APIRequestContext, method: 'GET' | 'PATCH' | 'DELETE', path: string, data?: Record<string, unknown>): Promise<{ status: number; body: T | null }> {
  const response = await request.fetch(`https://api.github.com${path}`, {
    method,
    headers: { Accept: 'application/vnd.github+json', Authorization: `Bearer ${GITHUB_TOKEN}`, 'X-GitHub-Api-Version': '2022-11-28' },
    ...(data ? { data } : {}),
  });
  const text = await response.text();
  return { status: response.status(), body: text.trim() ? JSON.parse(text) as T : null };
}
async function authenticate(page: Page): Promise<void> {
  reached('session-start');
  if (ACCOUNT_KEY) {
    const response = await page.context().request.post(`${APP_URL}/api/auth/account-key`, { data: { key: ACCOUNT_KEY } });
    expect(response.status(), 'A real backend login is required').toBe(200);
  }
  await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('sovereign-release-chat')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel('Session bestätigt')).toBeVisible({ timeout: 30_000 });
  const session = await page.context().request.get(`${APP_URL}/api/auth/me`);
  expect(session.status(), 'Backend must independently confirm the browser session').toBe(200);
  reached('session-verified');
}
async function provideCredential(page: Page): Promise<void> {
  // Exercise the actual production preflight against the ephemeral issued token,
  // without printing its value or treating format acceptance as authorization.
  expect(validateGitHubTokenFormat(GITHUB_TOKEN).isValid, 'Production preflight rejected the issued GitHub token format').toBe(true);
  await page.getByRole('button', { name: 'GitHub', exact: true }).click();
  await page.getByRole('group', { name: 'GitHub-Zugang' }).getByRole('button', { name: 'Zugang eingeben' }).click();
  await page.locator('#github-pat-input').fill(GITHUB_TOKEN);
  await page.getByRole('button', { name: 'Übernehmen' }).click();
  await expect(page.getByTestId('github-access-modal')).toBeHidden();
  reached('credential-input-accepted-not-authorized');
}
async function submitMission(page: Page): Promise<void> {
  const mission = [
    `Erstelle die Datei ${CANARY_PATH}.`,
    `Der Dateiinhalt muss exakt "${MARKER}" sein.`,
    'Ändere sonst keine Datei.',
    'Führe die notwendigen Repository-Prüfungen aus und erstelle anschließend einen Draft PR.',
    REPO_URL,
  ].join(' ');
  await page.getByLabel('Nachricht an Sovereign').fill(mission);
  await page.getByRole('button', { name: 'Senden' }).click();
  await expect(page.getByRole('button', { name: 'Repository-Ausführung starten' })).toBeVisible({ timeout: 120_000 });
  reached('mission-preview-visible');
}
async function readLinkedJob(page: Page): Promise<JobReadback> {
  const response = await page.context().request.get(`${APP_URL}/api/user/agent/jobs/${encodeURIComponent(linkedJobId)}`);
  expect(response.status(), 'Linked job must be readable by this exact session').toBe(200);
  const payload = await response.json() as { job?: JobReadback } & JobReadback;
  const job = payload.job || payload;
  expect(job.jobId || job.id).toBe(linkedJobId);
  if (['blocked', 'failed', 'cleaned'].includes(job.status || '')) {
    throw new Error(`Real repository job ${job.status}: ${redactDiagnostic(job.lastError || job.blocker || 'No diagnostic returned')}`);
  }
  return job;
}
async function executeMission(page: Page): Promise<void> {
  reached('repository-execution-start');
  const responsePromise = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/user/agent/swarm/run', { timeout: 600_000 });
  await page.getByRole('button', { name: 'Repository-Ausführung starten' }).click();
  const response = await responsePromise;
  const payload = await response.json().catch(() => ({})) as { jobId?: string; error?: string; reason?: string; blocker?: string };
  linkedJobId = typeof payload.jobId === 'string' ? payload.jobId : '';
  if (!linkedJobId) throw new Error(`Repository execution HTTP ${response.status()}: ${redactDiagnostic(payload.error || payload.reason || payload.blocker || 'No linked job')}`);
  // A 503 with a linked job is not a transport failure; inspect that real job.
  await readLinkedJob(page);
  reached('repository-job-linked');
  const deadline = Date.now() + 720_000;
  let continuations = 0;
  while (Date.now() < deadline) {
    const draft = page.getByRole('button', { name: 'Draft PR erstellen', exact: true });
    if (await draft.isVisible() && await draft.isEnabled()) {
      reached('draft-pr-preview-visible');
      return;
    }
    await readLinkedJob(page);
    const follow = page.getByRole('button', { name: 'Ausführung weiter verfolgen', exact: true });
    if (await follow.isVisible() && await follow.isEnabled()) {
      if (++continuations > 3) throw new Error('The same repository job did not reach Draft PR readiness after three continuations');
      await follow.click();
    }
    await page.waitForTimeout(2500);
  }
  throw new Error('Real repository job did not reach the visible Draft PR confirmation');
}
async function createThroughFrontend(page: Page): Promise<string> {
  reached('draft-pr-create');
  const responsePromise = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname === `/api/user/agent/jobs/${encodeURIComponent(linkedJobId)}/draft-pr/create`, { timeout: 180_000 });
  await page.getByRole('button', { name: 'Draft PR erstellen', exact: true }).click();
  const response = await responsePromise;
  const payload = await response.json() as { draftPrCreate?: { prUrl?: string; prNumber?: number; publishedHeadSha?: string; readbackHeadSha?: string } };
  const creation = payload.draftPrCreate;
  if (creation?.prNumber) createdPrNumber = creation.prNumber;
  expect(response.ok(), `Draft PR creation HTTP ${response.status()}`).toBe(true);
  const url = creation?.prUrl || '';
  const { owner, repo } = coordinates();
  expect(url.startsWith(`https://github.com/${owner}/${repo}/pull/`)).toBe(true);
  expect(createdPrNumber).toBeGreaterThan(0);
  backendPublishedHead = creation?.publishedHeadSha || '';
  expect(backendPublishedHead).toMatch(/^[0-9a-f]{40}$/);
  expect(creation?.readbackHeadSha).toBe(backendPublishedHead);
  await expect(page.getByText(url, { exact: false })).toBeVisible({ timeout: 30_000 });
  return url;
}
async function verifyOnGitHub(request: APIRequestContext, prUrl: string): Promise<void> {
  const { owner, repo } = coordinates();
  const base = `/repos/${owner}/${repo}`;
  const pull = await githubJson<PullReadback>(request, 'GET', `${base}/pulls/${createdPrNumber}`);
  expect(pull.status).toBe(200);
  const body = pull.body!;
  expect(body.html_url).toBe(prUrl);
  expect(body.state).toBe('open');
  expect(body.draft).toBe(true);
  expect(body.merged_at).toBeNull();
  expect(body.base.ref).toBe('main');
  expect(body.head.ref).toMatch(/^sovereign\/agent-/);
  expect(body.head.sha).toBe(backendPublishedHead);
  const files = await githubJson<{ filename: string }[]>(request, 'GET', `${base}/pulls/${createdPrNumber}/files?per_page=100`);
  expect(files.status).toBe(200);
  expect(files.body?.map(file => file.filename)).toEqual([CANARY_PATH]);
  const file = await githubJson<{ encoding: string; content: string }>(request, 'GET', `${base}/contents/${CANARY_PATH}?ref=${body.head.sha}`);
  expect(file.status).toBe(200);
  expect(file.body?.encoding).toBe('base64');
  const content = Buffer.from(file.body!.content, 'base64').toString('utf8');
  expect([MARKER, `${MARKER}\n`]).toContain(content);
  evidence = {
    runId: RUN_ID, marker: MARKER, path: CANARY_PATH,
    authMode: ACCOUNT_KEY ? 'account-key' : 'guest', jobId: linkedJobId,
    prNumber: body.number, prUrl: body.html_url, headRef: body.head.ref,
    headSha: body.head.sha, baseRef: body.base.ref, stateAtVerification: body.state,
    draftVerified: true, canaryFileVerified: true, markerVerified: true,
    closedAfterVerification: false, branchDeletedAfterVerification: false,
  };
  reached('github-draft-pr-verified');
}
async function cleanupOwnedCanary(request: APIRequestContext): Promise<void> {
  // Never close/delete a branch whose unique canary ownership was not proven.
  if (!evidence) return;
  const { owner, repo } = coordinates();
  const base = `/repos/${owner}/${repo}`;
  const pull = await githubJson<PullReadback>(request, 'GET', `${base}/pulls/${evidence.prNumber}`);
  expect(pull.status).toBe(200);
  expect(pull.body?.head.sha).toBe(evidence.headSha);
  expect(pull.body?.head.ref).toBe(evidence.headRef);
  expect(pull.body?.draft).toBe(true);
  expect(pull.body?.merged_at).toBeNull();
  const closed = await githubJson(request, 'PATCH', `${base}/pulls/${evidence.prNumber}`, { state: 'closed' });
  expect(closed.status).toBe(200);
  const closedReadback = await githubJson<PullReadback>(request, 'GET', `${base}/pulls/${evidence.prNumber}`);
  expect(closedReadback.status).toBe(200);
  expect(closedReadback.body?.state).toBe('closed');
  evidence.closedAfterVerification = true;
  const ref = evidence.headRef.split('/').map(encodeURIComponent).join('/');
  const head = await githubJson<{ object: { sha: string } }>(request, 'GET', `${base}/git/ref/heads/${ref}`);
  expect(head.status).toBe(200);
  expect(head.body?.object.sha).toBe(evidence.headSha);
  expect((await githubJson(request, 'DELETE', `${base}/git/refs/heads/${ref}`)).status).toBe(204);
  expect((await githubJson(request, 'GET', `${base}/git/ref/heads/${ref}`)).status).toBe(404);
  evidence.branchDeletedAfterVerification = true;
  reached('owned-canary-cleanup-verified');
}

test.use({ viewport: { width: 390, height: 844 }, trace: 'off', screenshot: 'off', video: 'off' });
test.describe.configure({ mode: 'serial' });
test.setTimeout(1_500_000);
test.describe('current release frontend creates one GitHub-verified Draft PR', () => {
  test.skip(!LIVE_ENABLED, 'External mutations run only in the explicitly enabled live lane.');
  test.beforeAll(() => {
    if (!GITHUB_TOKEN || !REPO_URL) throw new Error('Live canary GitHub credential/repository configuration is missing');
    coordinates();
  });
  test.beforeEach(async ({ page }) => {
    page.on('pageerror', error => console.error('CANARY_PAGE_ERROR', redactDiagnostic(error.message)));
    page.on('response', async response => {
      const path = new URL(response.url()).pathname;
      if (response.ok() || !path.startsWith('/api/')) return;
      console.error('CANARY_HTTP_FAILURE', response.status(), path);
      try {
        const body = await response.json();
        const detail = body.error || body.reason || body.blocker || body.job?.lastError;
        if (typeof detail === 'string') console.error('CANARY_FAILURE_DETAIL', redactDiagnostic(detail));
      } catch { /* Diagnostics cannot authorize an action or make a test pass. */ }
    });
  });
  test.afterEach(async ({ request }, info) => {
    try { await cleanupOwnedCanary(request); }
    finally {
      await mkdir('test-results', { recursive: true });
      await writeFile('test-results/frontend-draft-pr-live-evidence.json', JSON.stringify({
        verified: info.status === 'passed' && Boolean(evidence?.closedAfterVerification && evidence?.branchDeletedAfterVerification),
        frontendRevision: process.env.GITHUB_SHA || null,
        testSurface: 'CI_PREVIEW_WITH_LIVE_BACKEND', phase, observations,
        linkedJobId: linkedJobId || null, createdPrNumber: createdPrNumber || null,
        failure: info.errors.map(error => redactDiagnostic(error.message)), evidence,
      }, null, 2) + '\n');
    }
  });
  test('frontend -> backend job -> workspace -> Draft PR -> GitHub readback', async ({ page, request }) => {
    await authenticate(page);
    await provideCredential(page);
    await submitMission(page);
    await executeMission(page);
    const prUrl = await createThroughFrontend(page);
    await verifyOnGitHub(request, prUrl);
  });
});
