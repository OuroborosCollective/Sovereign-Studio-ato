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
