import { describe, expect, it, vi } from 'vitest';
import {
  OPEN_PR_REVIEW_ENDPOINT,
  fetchOpenPrReviewEvidence,
  formatOpenPrReviewEvidence,
} from './githubOpenPrReviewRuntime';
import type { DevChatRepoSnapshot } from './devChatWorkerBridge';

const SNAPSHOT: DevChatRepoSnapshot = {
  owner: 'OuroborosCollective',
  repo: 'Sovereign-Studio-ato',
  branch: 'main',
  name: 'Sovereign-Studio-ato',
  repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
  fileCount: 1,
  files: [],
  filePaths: [],
  dirs: [],
};

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('githubOpenPrReviewRuntime', () => {
  it('loads bounded read-only PR evidence without a client GitHub token', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.has('Authorization')).toBe(false);
      expect(init?.credentials).toBe('include');
      expect(JSON.parse(String(init?.body))).toEqual({
        owner: SNAPSHOT.owner,
        repo: SNAPSHOT.repo,
        limit: 20,
      });
      return response({
        ok: true,
        owner: SNAPSHOT.owner,
        repo: SNAPSHOT.repo,
        openPrCount: 1,
        reviewMode: 'read_only',
        githubWriteRequired: false,
        executorStarted: false,
        bounded: true,
        pullRequests: [{
          number: 1304,
          title: 'Fix runtime',
          url: 'https://github.com/example/repo/pull/1304',
          draft: true,
          headSha: 'a'.repeat(40),
          baseRef: 'main',
          mergeable: true,
          mergeableState: 'clean',
          changedFiles: 4,
          additions: 12,
          deletions: 3,
          filePaths: ['src/a.ts'],
          generatedArtifactCandidates: [],
          checkSummary: {
            successful: 3,
            pending: 1,
            failed: 0,
            failedNames: [],
            pendingNames: ['unit_tests'],
          },
          blockers: ['pending_checks'],
        }],
      });
    });

    const result = await fetchOpenPrReviewEvidence(SNAPSHOT, fetchMock as typeof fetch);

    expect(fetchMock).toHaveBeenCalledWith(OPEN_PR_REVIEW_ENDPOINT, expect.objectContaining({ method: 'POST' }));
    expect(result.ok).toBe(true);
    expect(result.evidence).toMatchObject({
      reviewMode: 'read_only',
      githubWriteRequired: false,
      executorStarted: false,
      openPrCount: 1,
    });
  });

  it('formats mergeability, checks and artifact candidates without claiming more than evidence', () => {
    const text = formatOpenPrReviewEvidence({
      ok: true,
      owner: 'acme',
      repo: 'tool',
      openPrCount: 1,
      reviewMode: 'read_only',
      githubWriteRequired: false,
      executorStarted: false,
      bounded: true,
      pullRequests: [{
        number: 7,
        title: 'Build output update',
        url: 'https://github.com/acme/tool/pull/7',
        draft: false,
        headSha: 'b'.repeat(40),
        baseRef: 'main',
        mergeable: false,
        mergeableState: 'blocked',
        changedFiles: 2,
        additions: 10,
        deletions: 1,
        filePaths: ['src/app.ts', 'dist/app.min.js'],
        generatedArtifactCandidates: ['dist/app.min.js'],
        checkSummary: {
          successful: 2,
          pending: 0,
          failed: 1,
          failedNames: ['typecheck'],
          pendingNames: [],
        },
        blockers: ['merge_conflict', 'mergeable_state:blocked', 'failed_checks'],
      }],
    });

    expect(text).toContain('#7 Build output update');
    expect(text).toContain('nicht mergeable (blocked)');
    expect(text).toContain('Fehlgeschlagene Checks: typecheck');
    expect(text).toContain('Generierte-Artefakt-Kandidaten: dist/app.min.js');
    expect(text).toContain('kein GitHub-Schreibzugang');
    expect(text).toContain('kein Executor');
  });
});
