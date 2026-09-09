import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { expect, test, type APIRequestContext } from '@playwright/test';

const APP_URL = 'https://sovereign-backend.arelorian.de/app/';
const API_ORIGIN = new URL(APP_URL).origin;
const REPOSITORY = 'OuroborosCollective/Sovereign-Studio-ato';
const EXPECTED_REVISION = process.env.SOVEREIGN_E2E_EXPECTED_REVISION || '';
const TOKEN = process.env.SOVEREIGN_E2E_GITHUB_TOKEN || '';
const ACCOUNT_KEY = process.env.SOVEREIGN_E2E_ACCOUNT_KEY || '';
const RUN_ID = process.env.GITHUB_RUN_ID || '';
const MARKER = `SOVEREIGN_PRODUCTION_DRAFT_PR:${RUN_ID}`;
const FILE_PATH = `docs/runtime-canary/frontend-draft-pr-production-${RUN_ID}.md`;
const record: Record<string, unknown> = { verified: false, surface: 'PRODUCTION_APP', appUrl: APP_URL,
  harnessRevision: process.env.GITHUB_SHA || null, expectedRuntimeRevision: EXPECTED_REVISION,
  runId: RUN_ID, marker: MARKER, path: FILE_PATH };
let phase = 'configuration';
function redact(value: unknown): string {
  let text = String(value);
  for (const secret of [TOKEN, ACCOUNT_KEY]) if (secret) text = text.split(secret).join('[redacted]');
  return text.replace(/\b(?:gh[pousr]_[A-Za-z0-9._-]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)/g, '[redacted]')
    .replace(/(Bearer\s+)\S+/gi, '$1[redacted]').slice(0, 1500);
}
function reached(next: string): void { phase = next; console.log('PRODUCTION_CANARY_PHASE', next); }
interface PullReadback {
  state: string; draft: boolean; merged_at: string | null; html_url: string;
  base: { ref: string }; head: { ref: string; sha: string; repo: { full_name: string } };
}
async function github<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`https://api.github.com/repos/${REPOSITORY}/${path}`, {
    headers: { Accept: 'application/vnd.github+json', Authorization: `Bearer ${TOKEN}`, 'X-GitHub-Api-Version': '2022-11-28' },
    maxRedirects: 0,
  });
  expect(response.status(), 'Independent GitHub readback').toBe(200);
  return response.json();
}
async function verifyServedRevision(request: APIRequestContext): Promise<void> {
  const response = await request.get(APP_URL, { maxRedirects: 0 });
  expect(response.status()).toBe(200);
  expect(response.headers()['x-sovereign-user-app-producer']).toBe('CANONICAL_CAPACITOR_WEB_APP');
  expect(response.headers()['x-sovereign-source-revision']).toBe(EXPECTED_REVISION);
  const html = await response.text();
  const scripts = [...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi)].map(match => new URL(match[1], APP_URL));
  expect(scripts.length).toBeGreaterThan(0);
  expect(scripts.length).toBeLessThanOrEqual(20);
  const assets: { url: string; sha256: string; bytes: number }[] = [];
  for (const url of scripts) {
    expect(url.origin, 'No credentials or requests to an unexpected asset origin').toBe(API_ORIGIN);
    const asset = await request.get(url.href, { maxRedirects: 0 });
    expect(asset.status()).toBe(200);
    const body = await asset.body();
    expect(body.length).toBeGreaterThan(0);
    expect(body.length).toBeLessThanOrEqual(10 * 1024 * 1024);
    assets.push({ url: url.href, sha256: createHash('sha256').update(body).digest('hex'), bytes: body.length });
  }
  record.observedRuntimeRevision = response.headers()['x-sovereign-source-revision'];
  record.htmlSha256 = createHash('sha256').update(html).digest('hex');
  record.servedEntryAssets = assets;
}

test.use({ viewport: { width: 390, height: 844 }, trace: 'off', screenshot: 'off', video: 'off' });
test.setTimeout(1_500_000);
test.skip(process.env.SOVEREIGN_E2E_PRODUCTION !== '1', 'Production mutations require an explicit production canary dispatch.');
test.afterEach(async ({}, info) => {
  record.verified = info.status === 'passed' && record.githubVerified === true && record.finalRevisionVerified === true;
  record.phase = phase;
  record.errors = info.errors.map(error => redact(error.message));
  await mkdir('test-results', { recursive: true });
  await writeFile('test-results/frontend-draft-pr-production-evidence.json', JSON.stringify(record, null, 2) + '\n');
  console.log('PRODUCTION_CANARY_RECEIPT', JSON.stringify(record));
});
test('deployed /app/ creates an independently GitHub-verified Draft PR', async ({ page, request }) => {
  expect(process.env.SOVEREIGN_E2E_PRODUCTION).toBe('1');
  expect(EXPECTED_REVISION).toMatch(/^[0-9a-f]{40}$/);
  expect(RUN_ID).toMatch(/^\d+$/);
  expect(TOKEN.length).toBeGreaterThan(0);
  reached('revision-preflight');
  await verifyServedRevision(request);
  const initialArtifact = JSON.stringify([record.htmlSha256, record.servedEntryAssets]);
  if (ACCOUNT_KEY) {
    const login = await page.context().request.post(`${API_ORIGIN}/api/auth/account-key`, { data: { key: ACCOUNT_KEY }, maxRedirects: 0 });
    expect(login.status()).toBe(200);
  }
  const navigation = await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
  expect(navigation?.status()).toBe(200);
  expect(page.url()).toBe(APP_URL);
  expect(navigation?.headers()['x-sovereign-source-revision']).toBe(EXPECTED_REVISION);
  await expect(page.getByTestId('sovereign-release-chat')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel('Session bestätigt')).toBeVisible({ timeout: 30_000 });
  expect((await page.context().request.get(`${API_ORIGIN}/api/auth/me`)).status()).toBe(200);
  reached('real-session-verified');
  await page.getByRole('button', { name: 'GitHub', exact: true }).click();
  await page.getByRole('group', { name: 'GitHub-Zugang' }).getByRole('button', { name: 'Zugang eingeben' }).click();
  await page.locator('#github-pat-input').fill(TOKEN);
  await page.getByRole('button', { name: 'Übernehmen' }).click();
  await expect(page.getByTestId('github-access-modal')).toBeHidden();
  const mission = `Erstelle die Datei ${FILE_PATH}. Der Dateiinhalt muss exakt "${MARKER}" sein. Ändere sonst keine Datei. Führe die notwendigen Repository-Prüfungen aus und erstelle anschließend einen Draft PR. https://github.com/${REPOSITORY}`;
  await page.getByLabel('Nachricht an Sovereign').fill(mission);
  await page.getByRole('button', { name: 'Senden' }).click();
  const start = page.getByRole('button', { name: 'Repository-Ausführung starten', exact: true });
  await expect(start).toBeVisible({ timeout: 120_000 });
  reached('frontend-mission-start');
  const runResponse = page.waitForResponse(response => response.request().method() === 'POST'
    && response.url() === `${API_ORIGIN}/api/user/agent/swarm/run`, { timeout: 600_000 });
  await start.click();
  const response = await runResponse;
  const run = await response.json().catch(() => ({}));
  record.startHttpStatus = response.status();
  if (typeof run.jobId !== 'string' || !run.jobId) throw new Error(`Mission start ${response.status()}: ${redact(run.error || run.reason || run.blocker || 'No job')}`);
  const jobId = run.jobId;
  record.jobId = jobId;
  reached('real-job-linked');
  const draftButton = page.getByRole('button', { name: 'Draft PR erstellen', exact: true });
  const deadline = Date.now() + 720_000;
  let continuations = 0;
  while (Date.now() < deadline) {
    const jobResponse = await page.context().request.get(`${API_ORIGIN}/api/user/agent/jobs/${encodeURIComponent(jobId)}`);
    expect(jobResponse.status()).toBe(200);
    const payload = await jobResponse.json();
    const job = payload.job || payload;
    expect(job.jobId || job.id).toBe(jobId);
    if (['blocked', 'failed', 'cleaned'].includes(job.status)) throw new Error(`Real job ${job.status}: ${redact(job.lastError || job.blocker)}`);
    if (await draftButton.isVisible() && await draftButton.isEnabled()) break;
    const follow = page.getByRole('button', { name: 'Ausführung weiter verfolgen', exact: true });
    if (await follow.isVisible() && await follow.isEnabled()) {
      if (++continuations > 3) throw new Error('Same job exceeded three continuations');
      await follow.click();
    }
    await page.waitForTimeout(2500);
  }
  await expect(draftButton).toBeVisible();
  await expect(draftButton).toBeEnabled();
  reached('frontend-draft-pr-create');
  const createResponse = page.waitForResponse(response => response.request().method() === 'POST'
    && response.url() === `${API_ORIGIN}/api/user/agent/jobs/${encodeURIComponent(jobId)}/draft-pr/create`, { timeout: 180_000 });
  await draftButton.click();
  const creationResponse = await createResponse;
  const creation = await creationResponse.json();
  if (!creationResponse.ok()) throw new Error(`Draft PR create ${creationResponse.status()}: ${redact(creation.error || creation.blocker)}`);
  const result = creation.draftPrCreate;
  expect(result?.prNumber).toBeGreaterThan(0);
  expect(result?.publishedHeadSha).toMatch(/^[0-9a-f]{40}$/);
  expect(result?.readbackHeadSha).toBe(result.publishedHeadSha);
  record.prNumber = result.prNumber;
  record.prUrl = result.prUrl;
  reached('independent-github-readback');
  const pr = await github<PullReadback>(request, `pulls/${result.prNumber}`);
  expect(pr.state).toBe('open');
  expect(pr.draft).toBe(true);
  expect(pr.merged_at).toBeNull();
  expect(pr.base.ref).toBe('main');
  expect(pr.head.repo.full_name).toBe(REPOSITORY);
  expect(pr.head.ref).toMatch(/^sovereign\/agent-/);
  expect(pr.head.sha).toBe(result.publishedHeadSha);
  expect(pr.html_url).toBe(result.prUrl);
  expect(pr.html_url).toBe(`https://github.com/${REPOSITORY}/pull/${result.prNumber}`);
  const files = await github<{ filename: string }[]>(request, `pulls/${result.prNumber}/files?per_page=100`);
  expect(files.map((file: { filename: string }) => file.filename)).toEqual([FILE_PATH]);
  const file = await github<{ encoding: string; content: string }>(request, `contents/${FILE_PATH}?ref=${pr.head.sha}`);
  expect(file.encoding).toBe('base64');
  expect([MARKER, `${MARKER}\n`]).toContain(Buffer.from(file.content, 'base64').toString('utf8'));
  await expect(page.getByText(pr.html_url, { exact: false })).toBeVisible({ timeout: 30_000 });
  record.headSha = pr.head.sha;
  record.headRef = pr.head.ref;
  record.githubVerified = true;
  await verifyServedRevision(request);
  expect(JSON.stringify([record.htmlSha256, record.servedEntryAssets])).toBe(initialArtifact);
  record.finalRevisionVerified = true;
  reached('production-to-github-verified');
});
