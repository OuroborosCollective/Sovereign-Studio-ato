import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RescuePanel } from './RescuePanel';

vi.mock('../billing/PaywallModal', () => ({
  PaywallModal: ({ isOpen }: { isOpen: boolean }) => (
    isOpen ? <div role="dialog" aria-label="Checkout">Bestehender Checkout</div> : null
  ),
}));

function response(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RescuePanel', () => {
  it('shows guided free diagnosis and a server-side paywall state', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockImplementationOnce(() => response({
        ok: true,
        csrfToken: 'csrf-bound-token',
        entitlement: {
          entitled: false,
          source: 'none',
          purchaseVerified: false,
          privileged: false,
          availableCredits: 500,
          requiredCredits: 10,
          repairPackId: 'rescue-repair-pack-v1',
          serverSideVerified: true,
          checkout: { required: true, surface: 'existing-paywall-modal', external: true },
        },
      }))
      .mockImplementationOnce(() => response({
        ok: true,
        diagnosis: {
          schemaVersion: 'sovereign.rescue.v1',
          ok: true,
          supported: true,
          mutationPerformed: false,
          repository: 'https://github.com/acme/app',
          baseBranch: 'main',
          baseSha: 'a'.repeat(40),
          failureFamily: 'github_actions_ci',
          failureFamilyTitle: 'GitHub Actions oder CI',
          riskClass: 'medium',
          affectedFiles: ['.github/workflows/ci.yml'],
          repairProposal: 'Workflow minimal korrigieren.',
          verificationPlan: ['required checks pass'],
          evidenceSha256: 'e'.repeat(64),
          outcomeContract: {
            contractSha256: 'c'.repeat(64),
            repairPack: {
              id: 'rescue-repair-pack-v1',
              credits: 10,
              maxChangedFiles: 12,
              maxRepairAttempts: 3,
              draftPrOnly: true,
              autoMerge: false,
            },
            successConditions: [],
            stopConditions: [],
          },
        },
      }));
    vi.stubGlobal('fetch', fetcher);
    render(
      <RescuePanel
        open
        apiBaseUrl="https://agent.example.test"
        onClose={() => undefined}
        onJobReady={() => undefined}
        onPublishDraftPr={() => undefined}
      />,
    );
    fireEvent.change(screen.getByLabelText('GitHub-Repository'), {
      target: { value: 'https://github.com/acme/app' },
    });
    fireEvent.change(screen.getByLabelText('Fehlerausgabe oder Logs'), {
      target: { value: 'GitHub Actions workflow failed' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Kostenlos diagnostizieren' }));
    await screen.findByText('GitHub Actions oder CI');
    expect(screen.getByText(/Repository wurde nicht verändert/)).toBeInTheDocument();
    expect(screen.getByText(/Kauf erforderlich/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Credits kaufen' }));
    expect(screen.getByRole('dialog', { name: 'Checkout' })).toBeInTheDocument();
  });

  it('shows incomplete ProofPack blockers instead of a false success', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockImplementationOnce(() => response({
        ok: true,
        csrfToken: 'csrf-bound-token',
        entitlement: {
          entitled: true,
          source: 'verified_purchase',
          purchaseVerified: true,
          privileged: false,
          availableCredits: 100,
          requiredCredits: 10,
          repairPackId: 'rescue-repair-pack-v1',
          serverSideVerified: true,
          checkout: { required: false, surface: 'existing-paywall-modal', external: true },
        },
      }))
      .mockImplementationOnce(() => response({
        ok: true,
        diagnosis: {
          schemaVersion: 'sovereign.rescue.v1',
          ok: true,
          supported: true,
          mutationPerformed: false,
          repository: 'https://github.com/acme/app',
          baseBranch: 'main',
          baseSha: 'a'.repeat(40),
          failureFamily: 'docker_compose_container',
          failureFamilyTitle: 'Docker Compose oder Container',
          riskClass: 'medium',
          affectedFiles: ['compose.yaml'],
          repairProposal: 'Compose minimal korrigieren.',
          verificationPlan: ['docker compose config passes'],
          evidenceSha256: 'e'.repeat(64),
          outcomeContract: {
            contractSha256: 'c'.repeat(64),
            repairPack: {
              id: 'rescue-repair-pack-v1',
              credits: 10,
              maxChangedFiles: 12,
              maxRepairAttempts: 3,
              draftPrOnly: true,
              autoMerge: false,
            },
            successConditions: [],
            stopConditions: [],
          },
        },
      }))
      .mockImplementationOnce(() => response({
        ok: true,
        repair: {
          repairId: '11111111-1111-4111-8111-111111111111',
          jobId: 'agent-1',
          state: 'running',
          chargedCredits: 10,
        },
      }, 202))
      .mockImplementationOnce(() => response({
        ok: true,
        csrfToken: 'csrf-bound-token',
        entitlement: {
          entitled: true,
          source: 'verified_purchase',
          purchaseVerified: true,
          privileged: false,
          availableCredits: 90,
          requiredCredits: 10,
          repairPackId: 'rescue-repair-pack-v1',
          serverSideVerified: true,
          checkout: { required: false, surface: 'existing-paywall-modal', external: true },
        },
      }))
      .mockImplementationOnce(() => response({
        ok: false,
        proofPack: {
          ready: false,
          proofSha256: 'f'.repeat(64),
          baseSha: 'a'.repeat(40),
          draftPrUrl: 'https://github.com/acme/app/pull/1',
          changedFiles: ['compose.yaml'],
          blockers: ['ci_not_green'],
        },
      }, 409));
    vi.stubGlobal('fetch', fetcher);
    const onJobReady = vi.fn();
    const onPublishDraftPr = vi.fn();
    render(
      <RescuePanel
        open
        apiBaseUrl="https://agent.example.test"
        currentJobId="agent-1"
        draftPrUrl="https://github.com/acme/app/pull/1"
        onClose={() => undefined}
        onJobReady={onJobReady}
        onPublishDraftPr={onPublishDraftPr}
      />,
    );
    fireEvent.change(screen.getByLabelText('GitHub-Repository'), {
      target: { value: 'https://github.com/acme/app' },
    });
    fireEvent.change(screen.getByLabelText('Fehlerausgabe oder Logs'), {
      target: { value: 'docker compose unhealthy' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Kostenlos diagnostizieren' }));
    await screen.findByText('Docker Compose oder Container');
    fireEvent.click(screen.getByRole('button', { name: 'Repair Pack starten' }));
    await waitFor(() => expect(onJobReady).toHaveBeenCalledWith('agent-1'));
    fireEvent.change(screen.getByLabelText(/GitHub-Zugang für private Repositories/), {
      target: { value: 'github_pat_ephemeral_private_token' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Draft PR aus geprüfter Evidence erstellen' }));
    await waitFor(() => expect(onPublishDraftPr).toHaveBeenCalledWith('github_pat_ephemeral_private_token'));
    expect(screen.getByLabelText(/GitHub-Zugang für private Repositories/)).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: 'ProofPack prüfen' }));
    await screen.findByText(/ci_not_green/);
    expect(screen.getByText(/Unvollständig/)).toBeInTheDocument();
  });

  it('uses a fresh idempotency key after every new diagnosis contract', async () => {
    const repairKeys: string[] = [];
    let repairCount = 0;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (rawUrl, init) => {
      const url = String(rawUrl);
      if (url.endsWith('/entitlement')) {
        return response({
          ok: true,
          csrfToken: 'csrf-bound-token',
          entitlement: {
            entitled: true,
            source: 'verified_purchase',
            purchaseVerified: true,
            privileged: false,
            availableCredits: 100,
            requiredCredits: 10,
            repairPackId: 'rescue-repair-pack-v1',
            serverSideVerified: true,
            checkout: { required: false, surface: 'existing-paywall-modal', external: true },
          },
        });
      }
      if (url.endsWith('/diagnose')) {
        return response({
          ok: true,
          diagnosis: {
            schemaVersion: 'sovereign.rescue.v1',
            ok: true,
            supported: true,
            mutationPerformed: false,
            repository: 'https://github.com/acme/app',
            baseBranch: 'main',
            baseSha: 'a'.repeat(40),
            failureFamily: 'github_actions_ci',
            failureFamilyTitle: 'GitHub Actions oder CI',
            riskClass: 'medium',
            affectedFiles: ['.github/workflows/ci.yml'],
            repairProposal: 'Workflow minimal korrigieren.',
            verificationPlan: ['required checks pass'],
            evidenceSha256: 'e'.repeat(64),
            outcomeContract: {
              contractSha256: 'c'.repeat(64),
              repairPack: {
                id: 'rescue-repair-pack-v1',
                credits: 10,
                maxChangedFiles: 12,
                maxRepairAttempts: 3,
                draftPrOnly: true,
                autoMerge: false,
              },
              successConditions: [],
              stopConditions: [],
            },
          },
        });
      }
      if (url.endsWith('/repair')) {
        const requestHeaders = init?.headers as Record<string, string>;
        repairKeys.push(requestHeaders['Idempotency-Key']);
        repairCount += 1;
        return response({
          ok: true,
          repair: {
            repairId: `repair-${repairCount}`,
            jobId: `agent-${repairCount}`,
            state: 'running',
            chargedCredits: 10,
          },
        }, 202);
      }
      throw new Error(`Unexpected Rescue request: ${url}`);
    });
    vi.stubGlobal('fetch', fetcher);
    const onJobReady = vi.fn();
    render(
      <RescuePanel
        open
        apiBaseUrl="https://agent.example.test"
        onClose={() => undefined}
        onJobReady={onJobReady}
        onPublishDraftPr={() => undefined}
      />,
    );
    fireEvent.change(screen.getByLabelText('GitHub-Repository'), {
      target: { value: 'https://github.com/acme/app' },
    });
    fireEvent.change(screen.getByLabelText('Fehlerausgabe oder Logs'), {
      target: { value: 'first workflow failure' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Kostenlos diagnostizieren' }));
    await screen.findByText('GitHub Actions oder CI');
    fireEvent.click(screen.getByRole('button', { name: 'Repair Pack starten' }));
    await waitFor(() => expect(onJobReady).toHaveBeenCalledWith('agent-1'));

    fireEvent.change(screen.getByLabelText('Fehlerausgabe oder Logs'), {
      target: { value: 'second workflow failure' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Kostenlos diagnostizieren' }));
    await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith('/diagnose'))).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: 'Repair Pack starten' }));
    await waitFor(() => expect(onJobReady).toHaveBeenCalledWith('agent-2'));

    expect(repairKeys).toHaveLength(2);
    expect(repairKeys[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(repairKeys[1]).toMatch(/^[0-9a-f-]{36}$/);
    expect(repairKeys[1]).not.toBe(repairKeys[0]);
  });
});
