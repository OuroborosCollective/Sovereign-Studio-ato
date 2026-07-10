import { describe, expect, it, vi } from 'vitest';

import { createOpenHandsEnterpriseClient } from './openhandsEnterpriseClient';
import type { OpenHandsEnterpriseConfig } from './openhandsEnterpriseRuntime';

const readyConfig: OpenHandsEnterpriseConfig = {
  enabled: true,
  deploymentMode: 'external-agent-runtime',
  agentApiUrl: 'https://sovereign-backend.example/openhands',
  adminConsoleUrl: 'https://openhands.example',
  ready: true,
  reason: 'ready',
};

const sovereignConfig: OpenHandsEnterpriseConfig = {
  enabled: true,
  deploymentMode: 'sovereign-agent-backend',
  agentApiUrl: 'https://sovereign-backend.example',
  adminConsoleUrl: '',
  ready: true,
  reason: 'ready',
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('OpenHandsEnterpriseClient', () => {
  it('normalizes ohConvId into the stable openHandsId field', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      jobId: 'job_123',
      ohConvId: 'conv_real_456',
      status: 'running',
      changedFiles: [],
      events: [
        { at: 123, level: 'info', stage: 'openhands', message: 'Real OpenHands conversation created.' },
      ],
    }, 201)) as unknown as typeof fetch;

    const client = createOpenHandsEnterpriseClient({ config: readyConfig, fetcher, now: () => 999 });
    const snapshot = await client.startJob({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      mission: 'Inspect the repository and report readiness. Draft PR only when real changes are needed.',
    });

    expect(snapshot.jobId).toBe('job_123');
    expect(snapshot.openHandsId).toBe('conv_real_456');
    expect(snapshot.status).toBe('running');
    expect(snapshot.repoUrl).toBe('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
    expect(snapshot.branch).toBe('main');
    expect(snapshot.events[0]?.message).toContain('Real OpenHands');
  });

  it('prefers explicit openHandsId over conversation aliases', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      jobId: 'job_abc',
      openHandsId: 'explicit_runtime_id',
      conversationId: 'conversation_alias',
      sessionId: 'session_alias',
      status: 'running',
      changedFiles: [],
      events: [],
    })) as unknown as typeof fetch;

    const client = createOpenHandsEnterpriseClient({ config: readyConfig, fetcher, now: () => 999 });
    const snapshot = await client.getJob('job_abc');

    expect(snapshot.openHandsId).toBe('explicit_runtime_id');
  });

  it('uses backend details in thrown errors so blocked runtime stays visible', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      status: 'blocked',
      details: 'OpenHands API authentication failed',
    }, 502)) as unknown as typeof fetch;

    const client = createOpenHandsEnterpriseClient({ config: readyConfig, fetcher, now: () => 999 });

    await expect(client.getJob('job_blocked')).rejects.toThrow('OpenHands API authentication failed');
  });

  it('uses the internal Sovereign Agent endpoint with session credentials and unwraps job responses', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const fetcherMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init });
      return jsonResponse({
        ok: true,
        runtime: 'sovereign-agent',
        job: {
          jobId: 'agent-123',
          status: 'provisioning',
          executor: 'sovereign-local-runner',
          workspaceId: 'agent-123',
          events: [
            { at: 123, level: 'success', stage: 'workspace_created', message: 'Workspace created.' },
          ],
        },
      }, 201);
    });

    const client = createOpenHandsEnterpriseClient({ config: sovereignConfig, fetcher: fetcherMock as unknown as typeof fetch, now: () => 999 });
    const snapshot = await client.startJob({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      mission: 'Use internal runtime.',
    });

    expect(calls[0]?.url).toBe('https://sovereign-backend.example/api/user/agent/jobs');
    expect(calls[0]?.init).toEqual(expect.objectContaining({ method: 'POST', credentials: 'include' }));
    const init = calls[0]?.init as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body.executor).toBe('sovereign-local-runner');
    expect(body.provisionWorkspace).toBe(true);
    expect(body.cloneRepo).toBe(true);
    expect(snapshot.jobId).toBe('agent-123');
    expect(snapshot.status).toBe('provisioning');
    expect(snapshot.openHandsId).toBe('agent-123');
    expect(snapshot.events[0]?.stage).toBe('workspace_created');
  });

  it('reads and cancels internal Sovereign Agent jobs through the backend route', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const fetcherMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init });
      return jsonResponse({
        runtime: 'sovereign-agent',
        job: { jobId: 'agent-abc', status: 'blocked', blocker: 'Stopped by user.', changedFiles: [], events: [] },
      });
    });

    const client = createOpenHandsEnterpriseClient({ config: sovereignConfig, fetcher: fetcherMock as unknown as typeof fetch, now: () => 999 });
    await client.getJob('agent-abc');
    await client.cancelJob('agent-abc');

    expect(calls[0]?.url).toBe('https://sovereign-backend.example/api/user/agent/jobs/agent-abc');
    expect(calls[0]?.init?.credentials).toBe('include');
    expect(calls[1]?.url).toBe('https://sovereign-backend.example/api/user/agent/jobs/agent-abc/cancel');
    expect(calls[1]?.init?.credentials).toBe('include');
  });
});
