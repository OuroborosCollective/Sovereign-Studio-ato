import { mkdir, writeFile } from 'node:fs/promises';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const LIVE_ENABLED = process.env.SOVEREIGN_E2E_LIVE === '1';
const ACCOUNT_KEY = process.env.SOVEREIGN_E2E_ACCOUNT_KEY?.trim() || '';
const GITHUB_TOKEN = process.env.SOVEREIGN_E2E_GITHUB_TOKEN?.trim() || '';
const REPO_URL = process.env.SOVEREIGN_E2E_REPO_URL?.trim() || '';
const RUN_ID = process.env.GITHUB_RUN_ID?.trim() || `local-${Date.now()}`;
const OWNED_MARKER_PREFIX = `[live-vnext:${RUN_ID}:`;

interface DraftPrEvidence {
  path: string;
  marker: string;
  persistedRunId: string;
  prNumber: number;
  prUrl: string;
  headRef: string;
  readbackHeadSha: string;
  draft: true;
  stateAtVerification: 'open';
  readmeVerified: true;
  closedAfterVerification: boolean;
  branchDeletedAfterVerification: boolean;
}

const evidence: DraftPrEvidence[] = [];

test.use({
  viewport: { width: 390, height: 844 },
  trace: 'off',
  screenshot: 'off',
  video: 'off',
});

function assertLiveConfig(): void {
  const missing = [
    ['SOVEREIGN_E2E_ACCOUNT_KEY', ACCOUNT_KEY],
    ['SOVEREIGN_E2E_GITHUB_TOKEN', GITHUB_TOKEN],
    ['SOVEREIGN_E2E_REPO_URL', REPO_URL],
  ].filter(([, value]) => !value).map(([name]) => name);
  if (missing.length > 0) {
    throw new Error(`Live vNext E2E configuration missing: ${missing.join(', ')}`);
  }
  const parsed = new URL(REPO_URL);
  if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || parsed.pathname.split('/').filter(Boolean).length !== 2) {
    throw new Error('SOVEREIGN_E2E_REPO_URL must be an exact https://github.com/owner/repository URL.');
  }
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
  const body = text.trim() ? JSON.parse(text) as T : null;
  return { status: response.status(), body };
}

async function latestPullRequestNumber(request: APIRequestContext): Promise<number> {
  const { owner, repo } = repositoryCoordinates();
  const result = await githubJson<Array<{ number: number }>>(
    request,
    'GET',
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls?state=all&sort=created&direction=desc&per_page=1`,
  );
  if (result.status !== 200) throw new Error(`GitHub latest-PR preflight failed: HTTP ${result.status}`);
  return result.body?.[0]?.number ?? 0;
}

async function closeOwnedDraftPr(
  request: APIRequestContext,
  prNumber: number,
  headRef: string,
): Promise<{ closed: boolean; branchDeleted: boolean }> {
  const { owner, repo } = repositoryCoordinates();
  const closed = await githubJson(
    request,
    'PATCH',
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls/${prNumber}`,
    { state: 'closed' },
  );
  const encodedRef = headRef.split('/').map(encodeURIComponent).join('/');
  const deleted = await githubJson(
    request,
    'DELETE',
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/git/refs/heads/${encodedRef}`,
  );
  return {
    closed: closed.status === 200,
    branchDeleted: deleted.status === 204 || deleted.status === 404 || deleted.status === 422,
  };
}

async function cleanupOwnedRunPullRequests(request: APIRequestContext): Promise<void> {
  const { owner, repo } = repositoryCoordinates();
  const result = await githubJson<Array<{
    number: number;
    title: string;
    head: { ref: string };
  }>>(
    request,
    'GET',
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls?state=open&per_page=100`,
  );
  if (result.status !== 200 || !result.body) return;
  for (const pull of result.body) {
    if (!pull.title.includes(OWNED_MARKER_PREFIX)) continue;
    if (!pull.head.ref.startsWith('sovereign/agent-')) continue;
    await closeOwnedDraftPr(request, pull.number, pull.head.ref);
  }
}

async function authenticateVNext(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.getByTestId('sovereign-control-surface-vnext')).toBeVisible({ timeout: 30_000 });
  await page.getByTestId('operator-auth-btn').click();
  const dialog = page.getByRole('dialog', { name: 'Sovereign account session' });
  await expect(dialog).toBeVisible();

  if (await dialog.getByText('AUTHENTICATED', { exact: true }).count()) {
    await dialog.getByRole('button', { name: 'Close account session' }).click();
    return;
  }

  const accountKey = dialog.locator('#vnext-account-key');
  await expect(accountKey).toBeVisible({ timeout: 20_000 });
  await accountKey.fill(ACCOUNT_KEY);
  await dialog.getByRole('button', { name: 'AUTHENTICATE WITH ACCOUNT KEY' }).click();
  await expect(dialog.getByText('AUTHENTICATED', { exact: true })).toBeVisible({ timeout: 30_000 });
  await dialog.getByRole('button', { name: 'Close account session' }).click();
}

function mission(pathId: string): { marker: string; text: string } {
  const marker = `${OWNED_MARKER_PREFIX}${pathId}]`;
  return {
    marker,
    text: [
      `${marker} Repository: ${REPO_URL}`,
      'Ändere ausschließlich README.md: Hänge den Marker aus der ersten Missionszeile an die erste Markdown-Überschrift an.',
      'Erhalte den übrigen Inhalt, führe die passenden Regressionstests aus und erzeuge noch keinen Pull Request.',
      'Stoppe nach belegtem Workspace-Diff und Test-Evidence, damit der sichtbare Publication-Gate den Draft PR separat freigeben kann.',
    ].join('\n'),
  };
}

async function submitMission(page: Page, text: string): Promise<string> {
  const composer = page.getByTestId('mission__textarea');
  await expect(composer).toBeVisible();
  await composer.fill(text);
  await page.getByTestId('builder__start-task').click();
  const accepted = page.getByText(/PERSISTED RUN ACCEPTED :: \[run-[0-9a-f]+\]/).last();
  await expect(accepted).toBeVisible({ timeout: 45_000 });
  const rendered = await accepted.innerText();
  const match = rendered.match(/\[(run-[0-9a-f]+)\]/);
  if (!match) throw new Error(`vNext did not expose the persisted run id: ${rendered}`);
  return match[1];
}

async function approveDraftReadinessIfRequested(page: Page): Promise<boolean> {
  const dialog = page.getByRole('dialog', { name: 'HUMAN-IN-THE-LOOP // OWNER DIRECTIVE REQUIRED' });
  if (!await dialog.isVisible().catch(() => false)) return false;
  const approve = dialog.getByRole('button', { name: /> approve/i });
  if (!await approve.isVisible().catch(() => false)) {
    const text = await dialog.innerText();
    throw new Error(`Persisted run requested non-draft owner input during live vNext proof: ${text}`);
  }
  await approve.click();
  await expect(dialog).toBeHidden({ timeout: 30_000 });
  return true;
}

async function openPublication(page: Page): Promise<void> {
  const publishTab = page.getByRole('button', { name: /PUBLISH/ });
  if (await publishTab.isVisible().catch(() => false)) await publishTab.click();
  await expect(page.getByTestId('vnext-publication-inspector')).toBeVisible();
}

async function waitForPublicationGate(page: Page): Promise<void> {
  const deadline = Date.now() + 210_000;
  while (Date.now() < deadline) {
    if (await approveDraftReadinessIfRequested(page)) {
      await page.waitForTimeout(500);
      continue;
    }
    await openPublication(page);
    const gate = page.getByTestId('vnext-prepare-draft-pr');
    if (await gate.isVisible().catch(() => false)) return;
    await page.getByRole('button', { name: /COMMAND/ }).click();
    await page.waitForTimeout(1_500);
  }
  throw new Error('vNext did not reach READY_TO_PUBLISH within the bounded live-test window.');
}

async function publishAndVerifyInUi(page: Page): Promise<{ prNumber: number; readbackHeadSha: string; prUrl: string }> {
  await waitForPublicationGate(page);
  await openPublication(page);
  await page.getByTestId('vnext-prepare-draft-pr').click();
  const consent = page.getByTestId('vnext-draft-pr-consent');
  await expect(consent).toBeVisible({ timeout: 30_000 });
  await expect(consent.getByText('EXTERNAL WRITE CONSENT')).toBeVisible();
  await expect(consent.getByText(/No merge\. No push to main\./)).toBeVisible();
  await page.getByTestId('vnext-create-draft-pr').click();

  const panel = page.getByTestId('vnext-publication-inspector');
  await expect(panel.getByText('GITHUB READBACK VERIFIED')).toBeVisible({ timeout: 180_000 });
  await expect(panel.getByText('DRAFT PR VERIFIED')).toBeVisible();
  const panelText = await panel.innerText();
  const prMatch = panelText.match(/#(\d+)/);
  const shaMatch = panelText.match(/\b[0-9a-f]{40}\b/);
  const prUrl = await panel.getByRole('link', { name: 'OPEN VERIFIED DRAFT PR' }).getAttribute('href');
  if (!prMatch || !shaMatch || !prUrl) throw new Error(`Verified publication panel lacked PR/head evidence: ${panelText}`);
  return { prNumber: Number(prMatch[1]), readbackHeadSha: shaMatch[0], prUrl };
}

async function verifyReadmeAtHead(
  request: APIRequestContext,
  headSha: string,
  marker: string,
): Promise<void> {
  const { owner, repo } = repositoryCoordinates();
  const result = await githubJson<{ content?: string; encoding?: string }>(
    request,
    'GET',
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents/README.md?ref=${encodeURIComponent(headSha)}`,
  );
  if (result.status !== 200 || !result.body?.content || result.body.encoding !== 'base64') {
    throw new Error(`GitHub README readback failed at ${headSha}: HTTP ${result.status}`);
  }
  const readme = Buffer.from(result.body.content.replace(/\s+/g, ''), 'base64').toString('utf8');
  const firstHeading = readme.split(/\r?\n/).find((line) => /^#\s+/.test(line)) || '';
  expect(firstHeading).toContain(marker);
}

async function verifyAndCleanDraftPr(
  request: APIRequestContext,
  pathName: string,
  marker: string,
  persistedRunId: string,
  baselinePrNumber: number,
  ui: { prNumber: number; readbackHeadSha: string; prUrl: string },
): Promise<void> {
  expect(ui.prNumber).toBeGreaterThan(baselinePrNumber);
  const { owner, repo } = repositoryCoordinates();
  const result = await githubJson<{
    number: number;
    html_url: string;
    title: string;
    state: string;
    draft: boolean;
    merged_at: string | null;
    head: { ref: string; sha: string };
  }>(request, 'GET', `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls/${ui.prNumber}`);
  if (result.status !== 200 || !result.body) throw new Error(`GitHub PR verification failed: HTTP ${result.status}`);

  expect(result.body.title).toContain(marker);
  expect(result.body.state).toBe('open');
  expect(result.body.draft).toBe(true);
  expect(result.body.merged_at).toBeNull();
  expect(result.body.head.ref).toMatch(/^sovereign\/agent-/);
  expect(result.body.head.sha).toBe(ui.readbackHeadSha);
  expect(result.body.html_url).toBe(ui.prUrl);
  await verifyReadmeAtHead(request, result.body.head.sha, marker);

  const cleanup = await closeOwnedDraftPr(request, ui.prNumber, result.body.head.ref);
  expect(cleanup.closed).toBe(true);
  expect(cleanup.branchDeleted).toBe(true);

  evidence.push({
    path: pathName,
    marker,
    persistedRunId,
    prNumber: ui.prNumber,
    prUrl: result.body.html_url,
    headRef: result.body.head.ref,
    readbackHeadSha: result.body.head.sha,
    draft: true,
    stateAtVerification: 'open',
    readmeVerified: true,
    closedAfterVerification: cleanup.closed,
    branchDeletedAfterVerification: cleanup.branchDeleted,
  });
}

async function executeCanonicalVNextRun(
  page: Page,
  request: APIRequestContext,
  pathId: string,
): Promise<void> {
  const change = mission(pathId);
  const baseline = await latestPullRequestNumber(request);
  const persistedRunId = await submitMission(page, change.text);
  const ui = await publishAndVerifyInUi(page);
  await verifyAndCleanDraftPr(request, `vnext-${pathId}`, change.marker, persistedRunId, baseline, ui);
}

test.describe('five canonical vNext repository runs reach independently verified Draft PRs', () => {
  test.describe.configure({ mode: 'serial' });
  test.skip(!LIVE_ENABLED, 'Live vNext Draft-PR validation runs only through the explicit protected workflow.');
  test.setTimeout(300_000);

  test.beforeAll(() => assertLiveConfig());
  test.beforeEach(async ({ page }) => authenticateVNext(page));
  test.afterEach(async ({ request }) => cleanupOwnedRunPullRequests(request));
  test.afterAll(async () => {
    await mkdir('test-results', { recursive: true });
    await writeFile(
      'test-results/five-draft-pr-evidence.json',
      `${JSON.stringify({ runId: RUN_ID, verifiedDraftPrCount: evidence.length, evidence }, null, 2)}\n`,
      'utf8',
    );
    if (evidence.length !== 5) {
      throw new Error(`Expected exactly five GitHub-verified vNext Draft PR runs, received ${evidence.length}.`);
    }
  });

  for (const pathId of ['p1', 'p2', 'p3', 'p4', 'p5']) {
    test(`canonical vNext ${pathId}: session → persisted run → evidence → consent → GitHub readback`, async ({ page, request }) => {
      await executeCanonicalVNextRun(page, request, pathId);
    });
  }
});
