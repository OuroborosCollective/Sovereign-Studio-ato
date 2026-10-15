import { describe, expect, it, vi } from 'vitest';
import { SovereignAgentClient } from './sovereignAgentClient';
import type { SovereignAgentConfig } from './sovereignAgentRuntime';

const CONFIG: SovereignAgentConfig = {
  enabled: true,
  deploymentMode: 'sovereign-agent-backend',
  agentApiUrl: 'https://sovereign.example',
  ready: true,
  reason: 'test runtime ready',
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('SovereignAgentClient Draft PR execution evidence', () => {
  it('fails closed when the backend returns only a Draft PR URL', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      ok: true,
      jobId: 'job-1',
      draftPrCreate: {
        allowed: true,
        status: 'created',
        prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/9999',
      },
    })) as unknown as typeof fetch;
    const client = new SovereignAgentClient({ config: CONFIG, fetcher });

    await expect(client.createDraftPr('job-1')).rejects.toThrow(
      'no complete GitHub Draft-PR/head-SHA/check readback evidence',
    );
  });

  it('accepts an open Draft PR only when published SHA, PR readback and CI surfaces agree', async () => {
    const sha = 'a'.repeat(40);
    const fetcher = vi.fn(async () => jsonResponse({
      ok: true,
      jobId: 'job-2',
      draftPrCreate: {
        allowed: true,
        status: 'created',
        prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/9998',
        headSha: sha,
        publishedHeadSha: sha,
        readbackHeadSha: sha,
        prNumber: 9998,
        draftVerified: true,
        prStateVerified: 'open',
        headBranch: 'sovereign/test-draft-flow',
        baseBranch: 'main',
        readbackVerified: true,
        checksReadbackVerified: true,
        ciState: 'pending',
        checkRunCount: 3,
        checksPendingCount: 2,
        checksSuccessCount: 1,
        checksFailureCount: 0,
        statusContextCount: 0,
      },
    })) as unknown as typeof fetch;
    const client = new SovereignAgentClient({ config: CONFIG, fetcher });

    const result = await client.createDraftPr('job-2');

    expect(result.ok).toBe(true);
    expect(result.draftPrCreate.draftVerified).toBe(true);
    expect(result.draftPrCreate.publishedHeadSha).toBe(sha);
    expect(result.draftPrCreate.readbackHeadSha).toBe(sha);
    expect(result.draftPrCreate.checksReadbackVerified).toBe(true);
    expect(result.draftPrCreate.ciState).toBe('pending');
  });

  it('rehydrates publication only from a fresh current GitHub readback', async () => {
    const sha = 'e'.repeat(40);
    const fetcher = vi.fn(async () => jsonResponse({
      ok: true,
      jobId: 'job-current',
      reconciliationStatus: 'VERIFIED',
      currentGitHubDraftPrReadback: {
        jobId: 'job-current',
        prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/9996',
        prNumber: 9996,
        headSha: sha,
        publishedHeadSha: sha,
        readbackHeadSha: sha,
        draftVerified: true,
        prStateVerified: 'open',
        headBranch: 'sovereign/test-draft-flow',
        baseBranch: 'main',
        readbackVerified: true,
        checksReadbackVerified: true,
        ciState: 'pending',
        checkRunCount: 2,
        checksPendingCount: 1,
        checksSuccessCount: 1,
        checksFailureCount: 0,
        statusContextCount: 0,
        sourceHash: 'f'.repeat(64),
      },
    })) as unknown as typeof fetch;
    const client = new SovereignAgentClient({ config: CONFIG, fetcher });

    const result = await client.getPublicationReadback('job-current');

    expect(result?.jobId).toBe('job-current');
    expect(result?.readbackHeadSha).toBe(sha);
    expect(result?.draftVerified).toBe(true);
    expect(fetcher).toHaveBeenCalledWith(
      'https://sovereign.example/api/user/agent/jobs/job-current/publication-readback',
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('does not retain the historical publication when current GitHub reconciliation is unavailable', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      ok: true,
      jobId: 'job-stale',
      reconciliationStatus: 'CONTRADICTED',
      currentGitHubDraftPrReadback: null,
    })) as unknown as typeof fetch;
    const client = new SovereignAgentClient({ config: CONFIG, fetcher });

    await expect(client.getPublicationReadback('job-stale')).resolves.toBeUndefined();
  });

  it('rejects a Draft PR whose readback SHA differs from the workspace publication SHA', async () => {
    const published = 'b'.repeat(40);
    const readback = 'c'.repeat(40);
    const fetcher = vi.fn(async () => jsonResponse({
      ok: true,
      jobId: 'job-3',
      draftPrCreate: {
        allowed: true,
        status: 'created',
        prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/9997',
        headSha: readback,
        publishedHeadSha: published,
        readbackHeadSha: readback,
        prNumber: 9997,
        draftVerified: true,
        prStateVerified: 'open',
        headBranch: 'sovereign/test-draft-flow',
        baseBranch: 'main',
        readbackVerified: true,
        checksReadbackVerified: true,
        ciState: 'none',
        checkRunCount: 0,
        checksPendingCount: 0,
        checksSuccessCount: 0,
        checksFailureCount: 0,
        statusContextCount: 0,
      },
    })) as unknown as typeof fetch;
    const client = new SovereignAgentClient({ config: CONFIG, fetcher });

    await expect(client.createDraftPr('job-3')).rejects.toThrow(
      'no complete GitHub Draft-PR/head-SHA/check readback evidence',
    );
  });
});
