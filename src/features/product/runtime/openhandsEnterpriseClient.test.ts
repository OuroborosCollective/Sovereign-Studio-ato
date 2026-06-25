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
});
