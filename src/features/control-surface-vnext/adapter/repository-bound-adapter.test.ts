import { describe, expect, it, vi } from 'vitest';
import { buildRepositoryBoundRunRequest, SovereignProductionAdapter } from './repository-bound-adapter';
import type { SovereignAgentConfig } from '../../product/runtime/sovereignAgentRuntime';

describe('vNext repository-bound Draft-PR mission contract', () => {
  it('keeps a normal repository instruction in repository execution even without a GitHub URL', () => {
    expect(buildRepositoryBoundRunRequest('Please add the repository readme a smiley like this :)')).toEqual({
      mission: 'Please add the repository readme a smiley like this :)',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryBranch: 'main',
    });
  });

  it('keeps an explicit GitHub repository URL as a bounded target override', () => {
    expect(buildRepositoryBoundRunRequest(
      'Ändere README.md in https://github.com/OuroborosCollective/Sovereign-Studio-ato.',
    )).toEqual({
      mission: 'Ändere README.md in https://github.com/OuroborosCollective/Sovereign-Studio-ato.',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repositoryBranch: 'main',
    });
  });

  it('fails closed instead of silently enabling swarm on the Draft-PR-first path', () => {
    expect(() => buildRepositoryBoundRunRequest('Ändere README.md.', 'swarm')).toThrow(/single agent/i);
  });

  it('starts the vNext mission through the dedicated repository endpoint and returns the persisted job id', async () => {
    const config: SovereignAgentConfig = {
      enabled: true,
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://agent.example.test',
      ready: true,
      reason: 'ready',
    };
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      ok: true,
      jobId: 'agent-repository-1',
      job: { jobId: 'agent-repository-1' },
    }), { status: 202 }));
    const adapter = new SovereignProductionAdapter(fetcher as unknown as typeof fetch, config);

    const accepted = await adapter.runSwarm('Ändere README.md.', [], [], 'single');

    expect(accepted).toEqual({ jobId: 'agent-repository-1' });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe('https://agent.example.test/api/user/agent/repository/run');
    const init = fetcher.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      mission: 'Ändere README.md.',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryBranch: 'main',
    });
  });

  it('restores the newest persisted repository job through authenticated backend readback without dispatching a replacement run', async () => {
    const config: SovereignAgentConfig = {
      enabled: true,
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://agent.example.test',
      ready: true,
      reason: 'ready',
    };
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => new Response(JSON.stringify({
      jobs: [
        {
          jobId: 'agent-unrelated-latest',
          mission: 'Non-repository background work.',
          status: 'running',
          repoUrl: null,
          branch: null,
        },
        {
          jobId: 'agent-persisted-latest',
          mission: 'Fix the persisted run.',
          status: 'running',
          repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
          branch: 'main',
        },
      ],
      total: 2,
    }), { status: init?.method === 'POST' ? 500 : 200 }));
    const adapter = new SovereignProductionAdapter(fetcher as unknown as typeof fetch, config);

    await expect(adapter.restoreLatestRepositoryRun()).resolves.toEqual({
      jobId: 'agent-persisted-latest',
      mission: 'Fix the persisted run.',
      status: 'running',
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
    });

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe('https://agent.example.test/api/user/agent/jobs?limit=20');
    expect((fetcher.mock.calls[0][1] as RequestInit).method).toBe('GET');
    expect((fetcher.mock.calls[0][1] as RequestInit).credentials).toBe('include');
  });

  it('fails closed when persisted repository job readback is malformed', async () => {
    const config: SovereignAgentConfig = {
      enabled: true,
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://agent.example.test',
      ready: true,
      reason: 'ready',
    };
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ jobs: 'not-an-array' }), { status: 200 }));
    const adapter = new SovereignProductionAdapter(fetcher as unknown as typeof fetch, config);

    await expect(adapter.restoreLatestRepositoryRun()).rejects.toThrow(/invalid jobs payload/i);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('checks vNext health through neutral jobs and does not read the Swarm manifest', async () => {
    const config: SovereignAgentConfig = {
      enabled: true,
      deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://agent.example.test',
      ready: true,
      reason: 'ready',
    };
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ jobs: [], total: 0 }), { status: 200 }));
    const adapter = new SovereignProductionAdapter(fetcher as unknown as typeof fetch, config);

    const health = await adapter.checkHealth();

    expect(health.status).toBe('ready');
    expect(fetcher.mock.calls[0][0]).toBe('https://agent.example.test/api/user/agent/jobs?limit=1');
    expect(String(fetcher.mock.calls[0][0])).not.toContain('/swarm/');
    await expect(adapter.getSkills()).resolves.toEqual([]);
  });
});
