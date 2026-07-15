import { mkdir, writeFile } from 'node:fs/promises';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const LIVE_ENABLED = process.env.SOVEREIGN_E2E_LIVE === '1';
const ACCOUNT_KEY = process.env.SOVEREIGN_E2E_ACCOUNT_KEY?.trim() || '';
const GITHUB_TOKEN = process.env.SOVEREIGN_E2E_GITHUB_TOKEN?.trim() || '';
const REPO_URL = process.env.SOVEREIGN_E2E_REPO_URL?.trim() || '';
const RUN_ID = process.env.GITHUB_RUN_ID?.trim() || `local-${Date.now()}`;
const OWNED_TITLE_PREFIX = `[live-five-path:${RUN_ID}:`;

interface DraftPrEvidence {
  path: string;
  marker: string;
  prNumber: number;
  prUrl: string;
  headRef: string;
  draft: true;
  stateAtVerification: 'open';
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
    throw new Error(`Live five-path E2E configuration missing: ${missing.join(', ')}`);
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
    if (!pull.title.includes(OWNED_TITLE_PREFIX)) continue;
    if (!pull.head.ref.startsWith('sovereign/agent-')) continue;
    await closeOwnedDraftPr(request, pull.number, pull.head.ref);
  }
}

async function loginAsFirstTimeUser(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.getByTestId('mission__textarea')).toBeVisible();
  if (await page.getByRole('button', { name: 'Profil' }).count()) return;
  await page.getByRole('button', { name: 'Anmelden', exact: true }).first().click();
  await page.getByPlaceholder('Optional: svk_ Account Key').fill(ACCOUNT_KEY);
  await page.getByRole('button', { name: 'Mit Account Key anmelden' }).click();
  await expect(page.getByRole('button', { name: 'Profil' })).toBeVisible({ timeout: 30_000 });
}

async function submitComposer(page: Page, text: string): Promise<void> {
  const composer = page.getByTestId('mission__textarea');
  await composer.fill(text);
  await page.getByTestId('builder__start-task').click();
}

async function waitForRepoReady(page: Page): Promise<void> {
  await expect(page.getByRole('button', { name: 'Repo Inspector öffnen' })).toBeVisible({ timeout: 45_000 });
}

async function loadRepoFromSideMenu(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Menü' }).click();
  const menu = page.getByTestId('sovereign-side-menu');
  await expect(menu).toBeVisible();
  await menu.getByRole('button').filter({ hasText: /Repo laden/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Repo Setup' });
  await dialog.getByRole('textbox', { name: 'GitHub Repository URL' }).fill(REPO_URL);
  await dialog.getByRole('button', { name: 'Repo-Snapshot laden' }).click();
  await waitForRepoReady(page);
}

async function loadRepoFromLauncher(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Tool Launcher öffnen' }).click();
  await page.getByRole('menuitem', { name: 'Repo', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Repo Setup' });
  await dialog.getByRole('textbox', { name: 'GitHub Repository URL' }).fill(REPO_URL);
  await dialog.getByRole('button', { name: 'Repo-Snapshot laden' }).click();
  await waitForRepoReady(page);
}

async function openGitHubAccessFromSideMenu(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Menü' }).click();
  const menu = page.getByTestId('sovereign-side-menu');
  await menu.getByRole('button').filter({ hasText: /GitHub Access/ }).click();
  await expect(page.getByRole('button', { name: 'Zugang eingeben' })).toBeVisible();
}

async function openGitHubAccessFromLauncher(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Tool Launcher öffnen' }).click();
  await page.getByRole('menuitem', { name: 'GitHub Access', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Zugang eingeben' })).toBeVisible();
}

async function provideGitHubAccess(page: Page): Promise<void> {
  const { owner, repo } = repositoryCoordinates();
  await page.getByRole('button', { name: 'Zugang eingeben' }).click();
  await page.locator('#github-pat-input').fill(GITHUB_TOKEN);
  const repoValidation = page.waitForResponse((response) =>
    response.request().method() === 'GET'
      && response.url() === `https://api.github.com/repos/${owner}/${repo}`,
  );
  await page.getByRole('button', { name: 'Übernehmen' }).click();
  const response = await repoValidation;
  expect(response.ok(), `GitHub UI validation returned HTTP ${response.status()}`).toBe(true);
  await expect(page.getByText(/GitHub-Zugang ist bereit/).last()).toBeVisible({ timeout: 30_000 });
}

async function confirmIntegrationIntent(page: Page): Promise<void> {
  const card = page.getByTestId('integration-intent-draft-card');
  await expect(card).toBeVisible({ timeout: 20_000 });
  const confirmButton = card.getByTestId('btn-confirm');
  await expect(confirmButton).toBeEnabled();
  await confirmButton.click();
}

async function confirmPatchDiff(page: Page): Promise<void> {
  const dialog = page.getByRole('dialog', { name: 'Patch Diff' });
  await expect(dialog).toBeVisible({ timeout: 45_000 });
  const confirmButton = dialog.getByTestId('confirm-patch-diff');
  await expect(confirmButton).toBeEnabled();
  await confirmButton.click();
  await expect(confirmButton).toHaveText(/Patch bestätigt/);
  await dialog.getByRole('button', { name: 'Patch Diff schließen' }).click();
  await expect(dialog).toBeHidden();
}

async function publishFromSideMenu(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Menü' }).click();
  const action = page.getByTestId('builder__draft-pr');
  await expect(action).toBeEnabled();
  await action.click();
}

async function publishFromSlashCommand(page: Page): Promise<void> {
  await submitComposer(page, '/pr');
}

async function verifyAndCleanDraftPr(
  page: Page,
  request: APIRequestContext,
  pathName: string,
  marker: string,
  baselinePrNumber: number,
): Promise<void> {
  const card = page.getByTestId('draft-pr-card');
  await expect(card).toBeVisible({ timeout: 180_000 });
  const cardText = await card.innerText();
  const match = cardText.match(/PR #(\d+)/);
  if (!match) throw new Error(`Draft PR card did not expose a PR number: ${cardText}`);
  const prNumber = Number(match[1]);
  expect(prNumber).toBeGreaterThan(baselinePrNumber);

  const { owner, repo } = repositoryCoordinates();
  const result = await githubJson<{
    number: number;
    html_url: string;
    title: string;
    state: string;
    draft: boolean;
    merged_at: string | null;
    head: { ref: string };
  }>(request, 'GET', `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls/${prNumber}`);
  if (result.status !== 200 || !result.body) throw new Error(`GitHub PR verification failed: HTTP ${result.status}`);

  expect(result.body.title).toContain(marker);
  expect(result.body.state).toBe('open');
  expect(result.body.draft).toBe(true);
  expect(result.body.merged_at).toBeNull();
  expect(result.body.head.ref).toMatch(/^sovereign\/agent-/);

  const cleanup = await closeOwnedDraftPr(request, prNumber, result.body.head.ref);
  expect(cleanup.closed).toBe(true);
  expect(cleanup.branchDeleted).toBe(true);

  evidence.push({
    path: pathName,
    marker,
    prNumber,
    prUrl: result.body.html_url,
    headRef: result.body.head.ref,
    draft: true,
    stateAtVerification: 'open',
    closedAfterVerification: cleanup.closed,
    branchDeletedAfterVerification: cleanup.branchDeleted,
  });
}

function instruction(pathId: string, emoji: string): { marker: string; text: string } {
  const marker = `${OWNED_TITLE_PREFIX}${pathId}]`;
  return {
    marker,
    text: `Füge ${emoji} in den README Titel ein. ${marker}`,
  };
}

test.describe('real first-user UI reaches five verified Draft PRs', () => {
  test.describe.configure({ mode: 'serial' });
  test.skip(!LIVE_ENABLED, 'Live five-path Draft-PR validation runs only through the explicit protected workflow.');
  test.setTimeout(240_000);

  test.beforeAll(() => assertLiveConfig());
  test.beforeEach(async ({ page }) => loginAsFirstTimeUser(page));
  test.afterEach(async ({ request }) => cleanupOwnedRunPullRequests(request));
  test.afterAll(async () => {
    await mkdir('test-results', { recursive: true });
    await writeFile(
      'test-results/five-draft-pr-evidence.json',
      `${JSON.stringify({ runId: RUN_ID, verifiedDraftPrCount: evidence.length, evidence }, null, 2)}\n`,
      'utf8',
    );
    if (evidence.length !== 5) {
      throw new Error(`Expected exactly five GitHub-verified Draft PR paths, received ${evidence.length}.`);
    }
  });

  test('path 1: repo URL in chat, intent first, access gate, side-menu Draft PR', async ({ page, request }) => {
    const change = instruction('p1', '🧭');
    const baseline = await latestPullRequestNumber(request);
    await submitComposer(page, REPO_URL);
    await waitForRepoReady(page);
    await submitComposer(page, change.text);
    await confirmIntegrationIntent(page);
    await provideGitHubAccess(page);
    await confirmPatchDiff(page);
    await publishFromSideMenu(page);
    await verifyAndCleanDraftPr(page, request, 'repo-url-intent-access-side-menu', change.marker, baseline);
  });

  test('path 2: slash repo, side-menu access first, integration confirmation, slash Draft PR', async ({ page, request }) => {
    const change = instruction('p2', '🧪');
    const baseline = await latestPullRequestNumber(request);
    await submitComposer(page, `/repo ${REPO_URL}`);
    await waitForRepoReady(page);
    await openGitHubAccessFromSideMenu(page);
    await provideGitHubAccess(page);
    await submitComposer(page, change.text);
    await confirmIntegrationIntent(page);
    await confirmPatchDiff(page);
    await publishFromSlashCommand(page);
    await verifyAndCleanDraftPr(page, request, 'slash-repo-side-access-slash-pr', change.marker, baseline);
  });

  test('path 3: side-menu repo, intent then card access, side-menu Draft PR', async ({ page, request }) => {
    const change = instruction('p3', '🔍');
    const baseline = await latestPullRequestNumber(request);
    await loadRepoFromSideMenu(page);
    await submitComposer(page, change.text);
    await confirmIntegrationIntent(page);
    await provideGitHubAccess(page);
    await confirmPatchDiff(page);
    await publishFromSideMenu(page);
    await verifyAndCleanDraftPr(page, request, 'side-repo-card-access-side-pr', change.marker, baseline);
  });

  test('path 4: launcher repo, launcher access first, slash Draft PR', async ({ page, request }) => {
    const change = instruction('p4', '🚀');
    const baseline = await latestPullRequestNumber(request);
    await loadRepoFromLauncher(page);
    await openGitHubAccessFromLauncher(page);
    await provideGitHubAccess(page);
    await submitComposer(page, change.text);
    await confirmIntegrationIntent(page);
    await confirmPatchDiff(page);
    await publishFromSlashCommand(page);
    await verifyAndCleanDraftPr(page, request, 'launcher-repo-launcher-access-slash-pr', change.marker, baseline);
  });

  test('path 5: task first, automatic repo/access resume, side-menu Draft PR', async ({ page, request }) => {
    const change = instruction('p5', '🛡️');
    const baseline = await latestPullRequestNumber(request);
    await submitComposer(page, change.text);
    const dialog = page.getByRole('dialog', { name: 'Repo Setup' });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('textbox', { name: 'GitHub Repository URL' }).fill(REPO_URL);
    await dialog.getByRole('button', { name: 'Repo-Snapshot laden' }).click();
    await waitForRepoReady(page);
    await expect(page.getByRole('button', { name: 'Zugang eingeben' })).toBeVisible({ timeout: 20_000 });
    await provideGitHubAccess(page);
    await confirmPatchDiff(page);
    await publishFromSideMenu(page);
    await verifyAndCleanDraftPr(page, request, 'task-first-auto-resume-side-pr', change.marker, baseline);
  });
});
