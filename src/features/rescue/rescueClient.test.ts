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
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        ok: true,
        csrfToken: 'csrf-bound-token',
        entitlement: { entitled: true },
      }))
      .mockResolvedValueOnce(jsonResponse({
        ok: true,
        repair: { repairId: 'repair-1', jobId: 'agent-1', state: 'running', chargedCredits: 10 },
      }, 202));
    const client = new SovereignRescueClient('https://agent.example.test', fetcher);
    await client.entitlement();
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      'https://agent.example.test/api/user/agent/rescue/entitlement',
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
        headers: expect.objectContaining({
          'X-Sovereign-Rescue-Origin': expect.any(String),
        }),
      }),
    );
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
          'X-Sovereign-Rescue-CSRF': 'csrf-bound-token',
          'X-Sovereign-Rescue-Origin': expect.any(String),
        }),
      }),
    );
  });

  it('downloads a revision-bound Capsule without sending patch or GitHub credentials', async () => {
    const archive = new Uint8Array([80, 75, 3, 4]);
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        ok: true,
        csrfToken: 'csrf-bound-token',
        entitlement: { entitled: true },
      }))
      .mockResolvedValueOnce(new Response(archive, {
        status: 200,
        headers: {
          'Content-Type': 'application/zip',
          'Content-Length': String(archive.byteLength),
          'Content-Disposition': 'attachment; filename="sovereign-repair-capsule-repair-1.zip"',
          'X-Sovereign-Capsule-Base-Sha': 'a'.repeat(40),
          'X-Sovereign-Capsule-Sha256': 'c'.repeat(64),
          'X-Sovereign-Mutation-Performed': 'false',
        },
      }));
    const client = new SovereignRescueClient('https://agent.example.test', fetcher);
    await client.entitlement();

    const download = await client.capsule('repair-1');

    expect(download.baseSha).toBe('a'.repeat(40));
    expect(download.capsuleSha256).toBe('c'.repeat(64));
    expect(download.filename).toBe('sovereign-repair-capsule-repair-1.zip');
    expect(download.archive.size).toBe(archive.byteLength);
    expect(download.mutationPerformed).toBe(false);
    const [, request] = fetcher.mock.calls[1];
    expect(request?.body).toBe('{}');
    expect(request?.headers).toEqual(expect.objectContaining({
      Accept: 'application/zip',
      'X-Sovereign-Rescue-CSRF': 'csrf-bound-token',
    }));
    expect(JSON.stringify(request)).not.toContain('githubAccessToken');
    expect(JSON.stringify(request)).not.toContain('patch');
  });

  it('returns backend blocker evidence on paywall and incomplete ProofPack states', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        ok: true,
        csrfToken: 'csrf-bound-token',
        entitlement: { entitled: true },
      }))
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
    await client.entitlement();
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
