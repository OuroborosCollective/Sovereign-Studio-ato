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
    expect(screen.queryByText(/github_pat_/)).not.toBeInTheDocument();
    const diagnosisRequest = JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body));
    expect(diagnosisRequest).not.toHaveProperty('githubAccessToken');
    expect(screen.getByText(/Repository wurde nicht verändert/)).toBeInTheDocument();
    expect(screen.getByText(/Kauf erforderlich/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Credits kaufen' }));
    expect(screen.getByRole('dialog', { name: 'Checkout' })).toBeInTheDocument();
  });

  it('shows incomplete ProofPack blockers instead of a false success', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockImplementationOnce(() => response({
        ok: true,
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
    render(
      <RescuePanel
        open
        apiBaseUrl="https://agent.example.test"
        currentJobId="agent-1"
        draftPrUrl="https://github.com/acme/app/pull/1"
        onClose={() => undefined}
        onJobReady={onJobReady}
        onPublishDraftPr={() => undefined}
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
    fireEvent.click(screen.getByRole('button', { name: 'ProofPack prüfen' }));
    await screen.findByText(/ci_not_green/);
    expect(screen.getByText(/Unvollständig/)).toBeInTheDocument();
  });

  it('rotates the repair idempotency key after diagnosis input changes', async () => {
    const entitlementPayload = {
      entitled: true,
      source: 'verified_purchase',
      purchaseVerified: true,
      privileged: false,
      availableCredits: 100,
      requiredCredits: 10,
      repairPackId: 'rescue-repair-pack-v1',
      serverSideVerified: true,
      checkout: { required: false, surface: 'existing-paywall-modal', external: true },
    };
    const diagnosisPayload = {
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
    };
    const fetcher = vi.fn<typeof fetch>()
      .mockImplementationOnce(() => response({ ok: true, entitlement: entitlementPayload }))
      .mockImplementationOnce(() => response({ ok: true, diagnosis: diagnosisPayload }))
      .mockImplementationOnce(() => response({
        ok: true,
        repair: {
          repairId: '11111111-1111-4111-8111-111111111111',
          jobId: 'agent-1',
          state: 'running',
          chargedCredits: 10,
        },
      }, 202))
      .mockImplementationOnce(() => response({ ok: true, entitlement: entitlementPayload }))
      .mockImplementationOnce(() => response({ ok: true, diagnosis: diagnosisPayload }))
      .mockImplementationOnce(() => response({
        ok: true,
        repair: {
          repairId: '22222222-2222-4222-8222-222222222222',
          jobId: 'agent-2',
          state: 'running',
          chargedCredits: 10,
        },
      }, 202))
      .mockImplementationOnce(() => response({ ok: true, entitlement: entitlementPayload }));
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
    const evidenceInput = screen.getByLabelText('Fehlerausgabe oder Logs');
    fireEvent.change(evidenceInput, {
      target: { value: 'GitHub Actions failed in .github/workflows/ci.yml' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Kostenlos diagnostizieren' }));
    await screen.findByText('GitHub Actions oder CI');
    fireEvent.click(screen.getByRole('button', { name: 'Repair Pack starten' }));
    await waitFor(() => expect(onJobReady).toHaveBeenCalledWith('agent-1'));
    const firstKey = (fetcher.mock.calls[2]?.[1]?.headers as Record<string, string>)['Idempotency-Key'];

    fireEvent.change(evidenceInput, {
      target: { value: 'GitHub Actions retry failed in .github/workflows/ci.yml' },
    });
    await waitFor(() => expect(screen.queryByText('GitHub Actions oder CI')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Kostenlos diagnostizieren' }));
    await screen.findByText('GitHub Actions oder CI');
    fireEvent.click(screen.getByRole('button', { name: 'Repair Pack starten' }));
    await waitFor(() => expect(onJobReady).toHaveBeenCalledWith('agent-2'));
    const secondKey = (fetcher.mock.calls[5]?.[1]?.headers as Record<string, string>)['Idempotency-Key'];

    expect(firstKey).toBeTruthy();
    expect(secondKey).toBeTruthy();
    expect(secondKey).not.toBe(firstKey);
  });
});
