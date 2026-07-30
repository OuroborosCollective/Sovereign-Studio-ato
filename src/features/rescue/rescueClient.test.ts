import { describe, expect, it, vi } from 'vitest';
import { SovereignRescueClient } from './rescueClient';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('SovereignRescueClient', () => {
  it('runs free diagnosis with credentials and without a write hint', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      ok: true,
      diagnosis: {
        ok: true,
        supported: true,
        mutationPerformed: false,
        baseSha: 'a'.repeat(40),
        failureFamily: 'github_actions_ci',
      },
    }));
    const client = new SovereignRescueClient('https://agent.example.test', fetcher);
    const diagnosis = await client.diagnose({
      repository: 'https://github.com/acme/app',
      baseBranch: 'main',
      evidenceText: 'workflow failed',
    });
    expect(diagnosis.mutationPerformed).toBe(false);
    expect(fetcher).toHaveBeenCalledWith(
      'https://agent.example.test/api/user/agent/rescue/diagnose',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
  });

  it('sends the repair idempotency key server-side', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      ok: true,
      repair: { repairId: 'repair-1', jobId: 'agent-1', state: 'running', chargedCredits: 10 },
    }, 202));
    const client = new SovereignRescueClient('https://agent.example.test', fetcher);
    const repair = await client.repair({
      repository: 'https://github.com/acme/app',
      baseBranch: 'main',
      evidenceText: 'docker compose failed',
      failureFamily: 'docker_compose_container',
      expectedBaseSha: 'a'.repeat(40),
    }, '11111111-1111-4111-8111-111111111111');
    expect(repair.jobId).toBe('agent-1');
    expect(fetcher).toHaveBeenCalledWith(
      'https://agent.example.test/api/user/agent/rescue/repair',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Idempotency-Key': '11111111-1111-4111-8111-111111111111',
        }),
      }),
    );
  });

  it('returns backend blocker evidence on paywall and incomplete ProofPack states', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ blocker: 'verified_purchase_required' }, 402))
      .mockResolvedValueOnce(jsonResponse({
        ok: false,
        proofPack: {
          ready: false,
          proofSha256: 'f'.repeat(64),
          baseSha: 'a'.repeat(40),
          changedFiles: [],
          blockers: ['ci_not_green'],
        },
      }, 409));
    const client = new SovereignRescueClient('https://agent.example.test', fetcher);
    await expect(client.repair({
      repository: 'https://github.com/acme/app',
      baseBranch: 'main',
      evidenceText: 'workflow failed',
      failureFamily: 'github_actions_ci',
      expectedBaseSha: 'a'.repeat(40),
    }, '11111111-1111-4111-8111-111111111111')).rejects.toMatchObject({
      status: 402,
      message: 'verified_purchase_required',
    });
    await expect(client.proofPack('repair-1')).rejects.toMatchObject({
      status: 409,
      payload: expect.objectContaining({
        proofPack: expect.objectContaining({ blockers: ['ci_not_green'] }),
      }),
    });
  });
});
