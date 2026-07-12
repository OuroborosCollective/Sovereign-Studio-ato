import { describe, expect, it, vi } from 'vitest';
import { SovereignAgentClient } from './sovereignAgentClient';
import { resolveSovereignAgentConfig } from './sovereignAgentRuntime';

const config = resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'https://agent.example.test' });

describe('SovereignAgentClient', () => {
  it('starts jobs only through /api/user/agent/jobs', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ job: { id: 'job-1', workspaceId: 'ws-1', status: 'queued', changedFiles: [], events: [] } }), { status: 201 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch, now: () => 10 });
    const snapshot = await client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' });
    expect(fetcher).toHaveBeenCalledWith('https://agent.example.test/api/user/agent/jobs', expect.objectContaining({ method: 'POST', credentials: 'include' }));
    expect(snapshot).toMatchObject({ jobId: 'job-1', runtimeId: 'ws-1', workspaceId: 'ws-1' });
  });
  it('polls and cancels through the same internal route family', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ id: 'job-1', status: 'running', changedFiles: [], events: [] }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });
    await client.getJob('job-1');
    await client.cancelJob('job-1');
    expect(fetcher.mock.calls[0][0]).toBe('https://agent.example.test/api/user/agent/jobs/job-1');
    expect(fetcher.mock.calls[1][0]).toBe('https://agent.example.test/api/user/agent/jobs/job-1/cancel');
  });
  it('surfaces backend blockers without compatibility aliases', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ blocker: 'workspace unavailable' }), { status: 409 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });
    await expect(client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })).rejects.toThrow('workspace unavailable');
  });
  it('sends confirmed staged files through a cloned workspace job', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      job: { id: 'job-staged', workspaceId: 'job-staged', status: 'running', changedFiles: ['README.md'], events: [] },
    }), { status: 201 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    await client.startJob({
      repoUrl: 'https://github.com/acme/repo',
      branch: 'main',
      mission: 'Update README',
      stagedFiles: [{ path: 'README.md', content: '# Updated\n', baseContent: '# Original\n' }],
      githubAccessToken: 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456',
    });

    const init = fetcher.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({ provisionWorkspace: true, cloneRepo: true });
    expect(body.stagedFiles).toEqual([{ path: 'README.md', content: '# Updated\n', baseContent: '# Original\n' }]);
    expect(body.githubAccessToken).toBe('ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456');
  });

  it('lists persisted jobs and continues the same job through prepare and create', async () => {
    const responses = [
      new Response(JSON.stringify({ jobs: [{ id: 'job-1', status: 'running', changedFiles: ['README.md'], events: [] }] }), { status: 200 }),
      new Response(JSON.stringify({ ok: true, jobId: 'job-1', draftPrPreparation: { allowed: true, decision: 'ready', blockers: [] } }), { status: 200 }),
      new Response(JSON.stringify({ ok: true, jobId: 'job-1', draftPrCreate: { allowed: true, status: 'created', prUrl: 'https://github.com/acme/repo/pull/7' } }), { status: 200 }),
    ];
    const fetcher = vi.fn(async () => responses.shift() as Response);
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    const jobs = await client.listJobs();
    const preparation = await client.prepareDraftPr(jobs[0].jobId || '');
    const creation = await client.createDraftPr(jobs[0].jobId || '', 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456');

    expect(jobs[0]).toMatchObject({ jobId: 'job-1', changedFiles: ['README.md'] });
    expect(preparation.draftPrPreparation.allowed).toBe(true);
    expect(creation.draftPrCreate.prUrl).toBe('https://github.com/acme/repo/pull/7');
    const createInit = fetcher.mock.calls[2][1] as RequestInit;
    expect(JSON.parse(String(createInit.body))).toEqual({ githubAccessToken: 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456' });
    expect(fetcher.mock.calls.map((call) => String(call[0]))).toEqual([
      'https://agent.example.test/api/user/agent/jobs',
      'https://agent.example.test/api/user/agent/jobs/job-1/draft-pr/prepare',
      'https://agent.example.test/api/user/agent/jobs/job-1/draft-pr/create',
    ]);
  });

  it('surfaces nested Draft-PR blockers from non-2xx responses', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      ok: false,
      draftPrPreparation: {
        allowed: false,
        blockers: ['Draft PR requires test evidence', 'Draft PR requires diff evidence'],
      },
    }), { status: 400 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    await expect(client.prepareDraftPr('job-1')).rejects.toThrow(
      'Draft PR requires test evidence; Draft PR requires diff evidence',
    );
  });

  it('carries chat work through predictive handoff and the real Draft-PR route family', async () => {
    const calls: string[] = [];
    const responses = [
      {
        ok: true,
        job: {
          id: 'job-flow',
          workspaceId: 'ws-flow',
          status: 'completed',
          repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
          branch: 'main',
          changedFiles: ['src/App.tsx'],
          events: [],
        },
        toolchain: {
          evidenceHash: 'a'.repeat(64),
          failureFamilies: [{
            code: 'typescript_contract_mismatch',
            title: 'TypeScript contract mismatch',
            severity: 'high',
            score: 3,
            checks: ['run targeted typecheck'],
          }],
          nextLogicalFailures: [1, 2, 3, 4].map(index => ({
            fromFamily: 'typescript_contract_mismatch',
            prediction: `Neighbouring runtime risk ${index}`,
            checkNext: `check ${index}`,
          })),
        },
      },
      {
        ok: true,
        jobId: 'job-flow',
        draftPrPreparation: {
          allowed: true,
          decision: 'ready',
          canCreateDraftPr: true,
          blockers: [],
        },
      },
      {
        ok: true,
        jobId: 'job-flow',
        draftPrCreate: {
          allowed: true,
          status: 'created',
          prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/999',
        },
      },
      {
        id: 'job-flow',
        workspaceId: 'ws-flow',
        status: 'completed',
        repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
        branch: 'main',
        draftPrUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/999',
        changedFiles: ['src/App.tsx'],
        events: [],
      },
    ];
    const fetcher = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
      calls.push(String(url));
      return new Response(JSON.stringify(responses.shift()), { status: 200 });
    });
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch, now: () => 10 });

    const job = await client.startToolchainJob({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      mission: 'Fix TypeScript and create a Draft PR.',
      evidenceText: 'TS2339 Property paymentMethods does not exist',
    });
    const preparation = await client.prepareDraftPr(job.jobId || '');
    const creation = await client.createDraftPr(job.jobId || '');
    const finalJob = await client.getJob(job.jobId || '');

    expect(job.events.filter(event => event.stage === 'toolchain_predictive_handoff')).toHaveLength(4);
    expect(preparation.draftPrPreparation.allowed).toBe(true);
    expect(creation.draftPrCreate.prUrl).toContain('/pull/999');
    expect(finalJob.draftPrUrl).toContain('/pull/999');
    expect(calls).toEqual([
      'https://agent.example.test/api/user/agent/toolchain/handoff',
      'https://agent.example.test/api/user/agent/jobs/job-flow/draft-pr/prepare',
      'https://agent.example.test/api/user/agent/jobs/job-flow/draft-pr/create',
      'https://agent.example.test/api/user/agent/jobs/job-flow',
    ]);
  });

  it('runs the deterministic janitor only through the owned job tool route', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      ok: true,
      jobId: 'job-1',
      tool: {
        status: 'done',
        stdout: 'Janitor scan completed: 1 finding(s). No files were changed.',
        changedFiles: [],
        metadata: { findings: [{ ruleId: 'PY-UNSAFE-SHELL' }], writeAction: false },
      },
    }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });
    const response = await client.runJanitor('job-1', { mode: 'scan', maxFindings: 10 });
    expect(fetcher).toHaveBeenCalledWith(
      'https://agent.example.test/api/user/agent/jobs/job-1/tools/janitor',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
    expect(response).toMatchObject({ ok: true, jobId: 'job-1', tool: { status: 'done', changedFiles: [] } });
  });
});
