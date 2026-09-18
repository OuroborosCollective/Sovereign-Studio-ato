import { randomBytes } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { expect, request as playwrightRequest, test, type Page } from '@playwright/test';
import {
  requireLoginAccountId,
  requireSameOrigin,
  requireVerifiedSessionIdentity,
} from './helpers/live-session-contract';

const LIVE_ENABLED = process.env.SOVEREIGN_E2E_LIVE === '1';
const CONFIGURED_ACCOUNT_KEY = process.env.SOVEREIGN_E2E_ACCOUNT_KEY?.trim() || '';
const REPO_URL = process.env.SOVEREIGN_E2E_REPO_URL?.trim() || '';
const BACKEND_URL = process.env.SOVEREIGN_E2E_BACKEND_PROXY_TARGET?.trim() || '';
const RUN_ID = process.env.GITHUB_RUN_ID?.trim() || `local-${Date.now()}`;
const JOB_ID = /^agent-[0-9a-f]{32}$/;
const A2A_REF = /^agent-zero-a2a:/;

let activeAccountKey = CONFIGURED_ACCOUNT_KEY;
let ephemeralAccountKeyId = '';
let ephemeralAccountId = '';
let ephemeralAccountKeyRevoked = false;
const identitySource = CONFIGURED_ACCOUNT_KEY
  ? 'protected_repository_secret'
  : 'ephemeral_product_registration';

test.use({
  viewport: { width: 390, height: 844 },
  trace: 'off',
  screenshot: 'off',
  video: 'off',
});

function assertLiveConfig(): void {
  if (!REPO_URL || !BACKEND_URL) throw new Error('LIVE_TESTFILE_CONFIG_MISSING');
  const repository = new URL(REPO_URL);
  if (
    repository.protocol !== 'https:'
    || repository.hostname !== 'github.com'
    || repository.pathname.split('/').filter(Boolean).length !== 2
  ) {
    throw new Error('LIVE_TESTFILE_REPOSITORY_URL_INVALID');
  }
  const backend = new URL(BACKEND_URL);
  if (backend.protocol !== 'https:' || !backend.hostname) {
    throw new Error('LIVE_TESTFILE_BACKEND_URL_INVALID');
  }
}

async function provisionEphemeralAccountKey(): Promise<void> {
  if (activeAccountKey) return;
  const api = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
  let password = `Sovereign-Testfile-${randomBytes(32).toString('base64url')}!9a`;
  const email = `live-testfile-${RUN_ID}-${randomBytes(8).toString('hex')}@tests.sovereign.invalid`;
  try {
    const registration = await api.post('/api/auth/register', {
      data: {
        email,
        password,
        displayName: `Sovereign Testfile Smoke ${RUN_ID}`,
      },
    });
    if (registration.status() !== 200) {
      throw new Error(`LIVE_TESTFILE_REGISTER_HTTP_${registration.status()}`);
    }
    const user = await registration.json() as {
      id?: string;
      isGuest?: boolean;
      credits?: number;
      creditStateVerified?: boolean;
    };
    if (
      !user.id
      || user.isGuest === true
      || user.creditStateVerified !== true
      || Number(user.credits || 0) <= 0
    ) {
      throw new Error('LIVE_TESTFILE_IDENTITY_INVALID');
    }

    const issued = await api.post('/api/security/account-keys', {
      data: { label: `Sovereign Testfile Smoke ${RUN_ID}` },
    });
    if (issued.status() !== 201) {
      throw new Error(`LIVE_TESTFILE_KEY_HTTP_${issued.status()}`);
    }
    const issuedBody = await issued.json() as { id?: string; key?: string };
    const key = String(issuedBody.key || '').trim();
    const keyId = String(issuedBody.id || '').trim();
    if (!key.startsWith('svk_') || !keyId) {
      throw new Error('LIVE_TESTFILE_KEY_INVALID');
    }
    activeAccountKey = key;
    ephemeralAccountKeyId = keyId;
    ephemeralAccountId = user.id;
  } finally {
    password = '';
    await api.dispose();
  }
}

async function revokeEphemeralAccountKey(): Promise<void> {
  if (!ephemeralAccountKeyId || !activeAccountKey) return;
  const api = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
  try {
    const login = await api.post('/api/auth/account-key', {
      data: { key: activeAccountKey },
    });
    if (login.status() !== 200) {
      throw new Error(`LIVE_TESTFILE_CLEANUP_LOGIN_HTTP_${login.status()}`);
    }
    const revoked = await api.delete(
      `/api/security/account-keys/${encodeURIComponent(ephemeralAccountKeyId)}`,
    );
    if (revoked.status() !== 200) {
      throw new Error(`LIVE_TESTFILE_KEY_REVOKE_HTTP_${revoked.status()}`);
    }
    ephemeralAccountKeyRevoked = true;
  } finally {
    activeAccountKey = '';
    await api.dispose();
  }
}

async function authenticate(page: Page): Promise<void> {
  if (!activeAccountKey) await provisionEphemeralAccountKey();
  await page.goto('/');
  await expect(page.getByTestId('sovereign-control-surface-vnext')).toBeVisible({
    timeout: 30_000,
  });

  await page.getByTestId('operator-auth-btn').click();
  const dialog = page.getByRole('dialog', { name: 'Sovereign account session' });
  await expect(dialog).toBeVisible();

  const accountKey = dialog.locator('#vnext-account-key');
  await expect(accountKey).toBeVisible({ timeout: 20_000 });
  await accountKey.fill(activeAccountKey);

  const authenticateButton = dialog.getByRole('button', {
    name: 'AUTHENTICATE WITH ACCOUNT KEY',
  });
  await expect(authenticateButton).toBeEnabled();

  const [login] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST'
        && new URL(response.url()).pathname === '/api/auth/account-key',
      { timeout: 30_000 },
    ),
    authenticateButton.click(),
  ]);

  requireSameOrigin(login.url(), page.url());
  const accountId = requireLoginAccountId(
    login.status(),
    await login.json().catch(() => null),
  );
  if (ephemeralAccountId && accountId !== ephemeralAccountId) {
    throw new Error('LIVE_TESTFILE_ACCOUNT_MISMATCH');
  }

  const session = await page.request.get(
    new URL('/api/auth/me', page.url()).href,
    {
      headers: { 'Cache-Control': 'no-store' },
      maxRedirects: 0,
    },
  );
  requireSameOrigin(session.url(), page.url());
  requireVerifiedSessionIdentity(
    session.status(),
    await session.json().catch(() => null),
    accountId,
  );

  await expect(dialog.getByText('AUTHENTICATED', { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await dialog.getByRole('button', { name: 'Close account session' }).click();
}

async function jobRead(page: Page, jobId: string) {
  const response = await page.request.get(
    new URL(
      `/api/user/agent/jobs/${encodeURIComponent(jobId)}`,
      page.url(),
    ).href,
    {
      headers: { 'Cache-Control': 'no-store' },
      maxRedirects: 0,
    },
  );
  requireSameOrigin(response.url(), page.url());
  expect(response.status()).toBe(200);
  const body = await response.json() as Record<string, unknown>;
  const job =
    typeof body.job === 'object' && body.job !== null
      ? body.job as Record<string, unknown>
      : body;
  return { body, job };
}

async function toolRead(
  page: Page,
  jobId: string,
  route: 'file' | 'git-status',
  data: Record<string, unknown>,
) {
  const response = await page.request.post(
    new URL(
      `/api/user/agent/jobs/${encodeURIComponent(jobId)}/tools/${route}`,
      page.url(),
    ).href,
    {
      data,
      headers: { 'Cache-Control': 'no-store' },
      maxRedirects: 0,
    },
  );
  requireSameOrigin(response.url(), page.url());
  const body = await response.json().catch(() => ({})) as Record<string, unknown>;
  const tool =
    typeof body.tool === 'object' && body.tool !== null
      ? body.tool as Record<string, unknown>
      : {};
  return { response, body, tool };
}

test.describe('one Sovereign frontend assignment reaches one Agent Zero task', () => {
  test.skip(
    !LIVE_ENABLED,
    'Live Agent Zero testfile smoke runs only through its explicit workflow.',
  );
  test.setTimeout(600_000);

  test.beforeAll(async () => {
    assertLiveConfig();
    await provisionEphemeralAccountKey();
  });

  test.afterAll(async () => {
    await revokeEphemeralAccountKey();
  });

  test('creates one empty root testfile through the Sovereign composer', async ({
    page,
  }) => {
    await authenticate(page);

    const mission = [
      `Repository: ${REPO_URL}`,
      'Erstelle im Root des bereitgestellten Repository-Workspaces genau eine leere reguläre Datei mit dem Namen testfile.',
      'Verändere keine andere Datei. Erzeuge keinen Commit und keinen Pull Request.',
      'Sobald testfile gespeichert ist, melde knapp: Auftrag abgeschlossen.',
    ].join('\n');

    const composer = page.getByTestId('mission__textarea');
    await expect(composer).toBeVisible();
    await composer.fill(mission);
    await expect(page.getByTestId('agent-mode-single')).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    const [startResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.request().method() === 'POST'
          && new URL(response.url()).pathname === '/api/user/agent/repository/run',
        { timeout: 120_000 },
      ),
      page.getByTestId('builder__start-task').click(),
    ]);

    requireSameOrigin(startResponse.url(), page.url());
    expect(startResponse.status()).toBe(202);
    const startBody = await startResponse.json() as Record<string, unknown>;
    const startJob =
      typeof startBody.job === 'object' && startBody.job !== null
        ? startBody.job as Record<string, unknown>
        : {};

    const jobId = String(
      startBody.jobId ?? startJob.jobId ?? startJob.id ?? '',
    );
    const workspaceId = String(
      startBody.workspaceId ?? startJob.workspaceId ?? '',
    );
    const initialExternalRef = String(
      startBody.externalRef ?? startJob.externalRef ?? '',
    );

    expect(jobId).toMatch(JOB_ID);
    expect(workspaceId).toBeTruthy();
    if (initialExternalRef) {
      expect(
        A2A_REF.test(initialExternalRef)
        || initialExternalRef.startsWith('agent-zero-a2a:pending:submit:'),
      ).toBe(true);
    }

    const accepted = page
      .getByText(/PERSISTED RUN ACCEPTED :: \[agent-[0-9a-f]{32}\]/)
      .last();
    await expect(accepted).toBeVisible({ timeout: 45_000 });

    let finalStatus = '';
    let finalExternalRef = initialExternalRef;
    let completionStage = '';
    let draftPrUrl: string | null = null;
    const deadline = Date.now() + 360_000;

    while (Date.now() < deadline) {
      const { body, job } = await jobRead(page, jobId);
      finalStatus = String(job.status ?? body.status ?? '');
      finalExternalRef = String(
        job.externalRef ?? body.externalRef ?? finalExternalRef,
      );
      draftPrUrl =
        typeof (job.draftPrUrl ?? body.draftPrUrl) === 'string'
          ? String(job.draftPrUrl ?? body.draftPrUrl)
          : null;

      const events = Array.isArray(job.events)
        ? job.events
        : Array.isArray(body.events)
          ? body.events
          : [];
      for (const raw of events) {
        if (!raw || typeof raw !== 'object') continue;
        const stage = String(
          (raw as Record<string, unknown>).stage ?? '',
        );
        if (
          stage.startsWith('repository_closeout_')
          || stage === 'repository_ready_for_draft_pr'
        ) {
          completionStage = stage;
        }
      }

      if (completionStage) break;
      await page.waitForTimeout(1_500);
    }

    expect(completionStage).toBeTruthy();
    expect(finalExternalRef).toMatch(A2A_REF);
    expect(draftPrUrl).toBeNull();

    const fileRead = await toolRead(
      page,
      jobId,
      'file',
      { mode: 'read', path: 'testfile', maxBytes: 1024 },
    );
    expect(String(fileRead.tool.status ?? '')).toBe('done');
    expect(String(fileRead.tool.stdout ?? fileRead.tool.output ?? '')).toBe('');

    const fileMetadata =
      typeof fileRead.tool.metadata === 'object'
      && fileRead.tool.metadata !== null
        ? fileRead.tool.metadata as Record<string, unknown>
        : {};
    expect(Number(fileMetadata.bytes ?? -1)).toBe(0);
    expect(String(fileMetadata.sha256 ?? '')).toMatch(/^[0-9a-f]{64}$/);

    const gitStatus = await toolRead(page, jobId, 'git-status', {});
    expect(String(gitStatus.tool.status ?? '')).toBe('done');

    const observedChangedFiles = Array.isArray(gitStatus.tool.changedFiles)
      ? gitStatus.tool.changedFiles.map(String)
      : [];
    const sovereignEvidenceFiles = observedChangedFiles.filter(
      (path) => path.startsWith('.security-reports/'),
    );
    const missionChangedFiles = observedChangedFiles.filter(
      (path) => !path.startsWith('.security-reports/'),
    );
    expect(missionChangedFiles).toEqual(['testfile']);
    expect(
      sovereignEvidenceFiles.every((path) => path.startsWith('.security-reports/')),
    ).toBe(true);

    let cleaned = false;
    if (['blocked', 'failed', 'completed', 'cleaned'].includes(finalStatus)) {
      const cleanup = await page.request.post(
        new URL(
          `/api/user/agent/jobs/${encodeURIComponent(jobId)}/cleanup`,
          page.url(),
        ).href,
        { data: {}, maxRedirects: 0 },
      );
      requireSameOrigin(cleanup.url(), page.url());
      expect(cleanup.status()).toBe(200);
      cleaned = true;
    }

    await mkdir('test-results', { recursive: true });
    await writeFile(
      'test-results/agent-zero-testfile-smoke.json',
      `${JSON.stringify({
        schemaVersion: 'sovereign.agent-zero-testfile-smoke.v1',
        sourceRevision: process.env.SOVEREIGN_E2E_REVISION || null,
        runId: RUN_ID,
        identitySource,
        ephemeralAccountKeyIssued: Boolean(ephemeralAccountKeyId),
        ephemeralAccountKeyRevoked,
        jobId,
        workspaceId,
        externalRef: finalExternalRef,
        completionStage,
        finalStatus,
        draftPrCreated: false,
        frontendSubmissionVerified: true,
        singleAgentModeVerified: true,
        fileReadback: {
          path: 'testfile',
          bytes: Number(fileMetadata.bytes ?? -1),
          sha256: String(fileMetadata.sha256 ?? ''),
          contentEmpty: true,
        },
        gitStatus: {
          changedFiles: missionChangedFiles,
          observedChangedFiles,
          sovereignEvidenceFiles,
        },
        workspaceCleanupPerformed: cleaned,
        sovereignWorkspaceReadbackVerified: true,
        secretValuesReturned: false,
      }, null, 2)}\n`,
      'utf8',
    );
  });
});
