import { mkdir, writeFile } from 'node:fs/promises';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const LIVE_ENABLED = process.env.SOVEREIGN_E2E_LIVE === '1';
const ACCOUNT_KEY = process.env.SOVEREIGN_E2E_ACCOUNT_KEY?.trim() || '';
const GITHUB_TOKEN = process.env.SOVEREIGN_E2E_GITHUB_TOKEN?.trim() || '';
const REPO_URL = process.env.SOVEREIGN_E2E_REPO_URL?.trim() || '';
const APP_URL = process.env.SOVEREIGN_E2E_APP_URL?.trim() || 'http://127.0.0.1:3000';
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

interface PullFileReadback {
  filename: string;
  status: string;
  patch?: string;
}

interface Evidence {
  runId: string;
  marker: string;
  path: string;
  authMode: 'account-key' | 'guest';
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
let createdPrNumber = 0;
let createdHeadRef = '';
let authMode: Evidence['authMode'] = ACCOUNT_KEY ? 'account-key' : 'guest';

test.use({
  viewport: { width: 390, height: 844 },
  trace: 'off',
  screenshot: 'off',
  video: 'off',
});

test.describe.configure({ mode: 'serial' });
test.setTimeout(1_500_000);

function assertLiveConfig(): void {
  const missing = [
    ['SOVEREIGN_E2E_GITHUB_TOKEN', GITHUB_TOKEN],
    ['SOVEREIGN_E2E_REPO_URL', REPO_URL],
  ].filter(([, value]) => !value).map(([name]) => name);
  if (missing.length > 0) throw new Error(`Live Draft-PR configuration missing: ${missing.join(', ')}`);

  const parsed = new URL(REPO_URL);
  if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com') {
    throw new Error('SOVEREIGN_E2E_REPO_URL must be an https://github.com repository URL.');
  }
  const parts = parsed.pathname.split('/').filter(Boolean);
  if (parts.length !== 2) throw new Error('SOVEREIGN_E2E_REPO_URL must identify exactly one repository.');
}

function repositoryCoordinates(): { owner: string; repo: string } {
  const parsed = new URL(REPO_URL);
  const [owner, repo] = parsed.pathname.split('/').filter(Boolean);
  return { owner, repo: repo.replace(/\.git$/i, '') };
}

function githubHeaders(): Record<string, string> {
  return {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${GITHUB_TOKEN}`,
    'X-GitHub-Api-Version': '2022-11-28',
  };
}

async function githubJson<T>(
  request: APIRequestContext,
  method: 'GET' | 'PATCH' | 'DELETE',
  path: string,
  data?: Record<string, unknown>,
): Promise<{ status: number; body: T | null }> {
  const response = await request.fetch(`https://api.github.com${path}`, {
    method,
    headers: githubHeaders(),
    ...(data ? { data } : {}),
  });
  const text = await response.text();
  return { status: response.status(), body: text.trim() ? JSON.parse(text) as T : null };
}

async function authenticateRealFrontendSession(page: Page): Promise<void> {
  if (ACCOUNT_KEY) {
    const response = await page.context().request.post(`${APP_URL}/api/auth/account-key`, {
      data: { key: ACCOUNT_KEY },
      headers: { 'Content-Type': 'application/json' },
    });
    expect(response.status(), 'Protected account-key login must create a real backend session').toBe(200);
    authMode = 'account-key';
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('button', { name: 'Abmelden' })).toBeVisible({ timeout: 30_000 });
  } else {
    authMode = 'guest';
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Gastzugang', { exact: true })).toBeVisible({ timeout: 30_000 });
  }
  await expect(page.getByLabel('Session bestätigt')).toBeVisible({ timeout: 30_000 });
}

async function provideRealGitHubWriteAccess(page: Page): Promise<void> {
  const { owner, repo } = repositoryCoordinates();
  await page.getByRole('button', { name: 'GitHub', exact: true }).click();
  const card = page.getByRole('group', { name: 'GitHub-Zugang' });
  await expect(card).toBeVisible();
  await card.getByRole('button', { name: 'Zugang eingeben' }).click();
  await page.locator('#github-pat-input').fill(GITHUB_TOKEN);
  const validation = page.waitForResponse((response) => (
    response.request().method() === 'GET'
    && response.url() === `https://api.github.com/repos/${owner}/${repo}`
  ), { timeout: 30_000 });
  await page.getByRole('button', { name: 'Übernehmen' }).click();
  const response = await validation;
  expect(response.ok(), `GitHub token validation returned HTTP ${response.status()}`).toBe(true);
  await expect(page.getByText(/GitHub .* nutzbar/)).toBeVisible({ timeout: 30_000 });
}

async function submitMission(page: Page): Promise<void> {
  const mission = [
    `Erstelle die Datei ${CANARY_PATH}.`,
    `Der Dateiinhalt muss exakt "${MARKER}" sein.`,
    'Ändere sonst keine Datei.',
    'Führe die notwendigen Repository-Prüfungen aus und erstelle anschließend einen Draft PR.',
    REPO_URL,
  ].join(' ');
  const composer = page.getByLabel('Nachricht an Sovereign');
  await composer.fill(mission);
  await page.getByRole('button', { name: 'Senden' }).click();
  await expect(page.getByRole('button', { name: 'Repository-Ausführung starten' })).toBeVisible({ timeout: 90_000 });
}

async function driveRepositoryRunToDraftReady(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Repository-Ausführung starten' }).click();
  for (let continuation = 0; continuation < 3; continuation += 1) {
    const draft = page.getByRole('button', { name: 'Draft PR erstellen' });
    const follow = page.getByRole('button', { name: 'Ausführung weiter verfolgen' });
    const outcome = await Promise.race([
      draft.waitFor({ state: 'visible', timeout: 660_000 }).then(() => 'draft' as const),
      follow.waitFor({ state: 'visible', timeout: 660_000 }).then(() => 'follow' as const),
    ]);
    if (outcome === 'draft') return;
    await follow.click();
  }
  await expect(page.getByRole('button', { name: 'Draft PR erstellen' })).toBeVisible({ timeout: 660_000 });
}

async function createDraftPrThroughFrontend(page: Page): Promise<string> {
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && response.url().includes('/draft-pr/create')
  ), { timeout: 180_000 });
  await page.getByRole('button', { name: 'Draft PR erstellen' }).click();
  const response = await responsePromise;
  const payload = await response.json().catch(() => ({})) as {
    draftPrCreate?: { prUrl?: string; prNumber?: number };
    prUrl?: string;
  };
  const prUrl = payload.draftPrCreate?.prUrl || payload.prUrl || '';
  if (payload.draftPrCreate?.prNumber) createdPrNumber = payload.draftPrCreate.prNumber;
  expect(response.ok(), `Frontend Draft-PR create route returned HTTP ${response.status()}`).toBe(true);
  expect(prUrl).toMatch(/^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+$/);
  if (!createdPrNumber) createdPrNumber = Number(prUrl.split('/').pop() || '0');
  await expect(page.getByText(prUrl, { exact: false })).toBeVisible({ timeout: 30_000 });
  return prUrl;
}

async function verifyDraftPrOnGitHub(request: APIRequestContext, prUrl: string): Promise<void> {
  const { owner, repo } = repositoryCoordinates();
  const pull = await githubJson<PullReadback>(request, 'GET', `/repos/${owner}/${repo}/pulls/${createdPrNumber}`);
  expect(pull.status).toBe(200);
  expect(pull.body).not.toBeNull();
  const body = pull.body!;
  createdHeadRef = body.head.ref;
  expect(body.html_url).toBe(prUrl);
  expect(body.state).toBe('open');
  expect(body.draft).toBe(true);
  expect(body.merged_at).toBeNull();
  expect(body.base.ref).toBe('main');
  expect(body.head.ref).toMatch(/^sovereign\/agent-/);
  expect(body.head.sha).toMatch(/^[0-9a-f]{40}$/);

  const files = await githubJson<PullFileReadback[]>(request, 'GET', `/repos/${owner}/${repo}/pulls/${createdPrNumber}/files?per_page=100`);
  expect(files.status).toBe(200);
  const changed = files.body || [];
  const canary = changed.find((entry) => entry.filename === CANARY_PATH);
  expect(canary, `Draft PR must contain ${CANARY_PATH}`).toBeDefined();
  expect(changed.map((entry) => entry.filename)).toEqual([CANARY_PATH]);
  expect(canary?.patch || '').toContain(MARKER);

  evidence = {
    runId: RUN_ID,
    marker: MARKER,
    path: CANARY_PATH,
    authMode,
    prNumber: body.number,
    prUrl: body.html_url,
    headRef: body.head.ref,
    headSha: body.head.sha,
    baseRef: body.base.ref,
    stateAtVerification: body.state,
    draftVerified: body.draft === true,
    canaryFileVerified: true,
    markerVerified: true,
    closedAfterVerification: false,
    branchDeletedAfterVerification: false,
  };
}

async function cleanupOwnedDraftPr(request: APIRequestContext): Promise<void> {
  if (!createdPrNumber || !createdHeadRef) return;
  const { owner, repo } = repositoryCoordinates();
  const closed = await githubJson(request, 'PATCH', `/repos/${owner}/${repo}/pulls/${createdPrNumber}`, { state: 'closed' });
  const encodedRef = createdHeadRef.split('/').map(encodeURIComponent).join('/');
  const deleted = await githubJson(request, 'DELETE', `/repos/${owner}/${repo}/git/refs/heads/${encodedRef}`);
  if (evidence) {
    evidence.closedAfterVerification = closed.status === 200;
    evidence.branchDeletedAfterVerification = deleted.status === 204 || deleted.status === 404 || deleted.status === 422;
  }
  expect(closed.status).toBe(200);
  expect([204, 404, 422]).toContain(deleted.status);
}

async function writeEvidence(): Promise<void> {
  await mkdir('test-results', { recursive: true });
  await writeFile(
    'test-results/frontend-draft-pr-live-evidence.json',
    `${JSON.stringify({ verified: Boolean(evidence), evidence }, null, 2)}\n`,
    'utf8',
  );
}

test.describe('current release frontend creates one GitHub-verified Draft PR', () => {
  test.skip(!LIVE_ENABLED, 'Real Draft-PR canary runs only in the protected live workflow.');
  test.beforeAll(() => assertLiveConfig());
  test.afterEach(async ({ request }) => {
    try {
      await cleanupOwnedDraftPr(request);
    } finally {
      await writeEvidence();
    }
  });

  test('frontend -> backend job -> workspace -> Draft PR -> GitHub readback', async ({ page, request }) => {
    await authenticateRealFrontendSession(page);
    await provideRealGitHubWriteAccess(page);
    await submitMission(page);
    await driveRepositoryRunToDraftReady(page);
    const prUrl = await createDraftPrThroughFrontend(page);
    await verifyDraftPrOnGitHub(request, prUrl);
  });
});
