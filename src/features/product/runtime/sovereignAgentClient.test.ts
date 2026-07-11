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
