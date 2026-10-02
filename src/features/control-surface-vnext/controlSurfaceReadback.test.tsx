import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SovereignProductionAdapter } from './adapter/repository-bound-adapter';
import { SkillRegistryDrawer } from './components/Skills/SkillRegistryDrawer';
import { IntegrationModal } from './components/IntegrationPlus/IntegrationModal';
import { ChatSurface } from './components/ChatSurface/ChatSurface';

const payload = () => ({
  schemaVersion: 'sovereign.control-surface-readback.v1', jobId: 'agent-real', observedAt: '2026-10-02T21:03:00+00:00',
  agentReadbackState: 'live', agents: [{ id: 'free_single_agent', name: 'free_single_agent', kind: 'agent',
    status: 'BLOCKED', persistedStatus: 'RUNNING', source: 'agents-sdk', jobId: 'agent-real',
    runId: 'repo-agent-real', taskId: 'task-real', description: 'Persisted agent task', updatedAt: '2026-10-02T21:02:00+00:00' }],
  integrationReadbackState: 'live', integrations: [{ id: 'r2', name: 'Cloudflare R2', status: 'defined_not_run',
    source: 'enterprise-platform-readback', observedAt: '2026-10-02T21:03:00+00:00', boundary: 'Object store',
    blocker: 'provider_head_canary_not_executed', readbackSha256: 'a'.repeat(64) }],
  credits: { readbackState: 'live', creditStateVerified: true, credits: 1250, providerFundedCredits: 1100,
    paidEntitlementVerified: true, paidEntitlementSource: 'verified_purchase' },
  routing: { repositoryMode: 'free', agentMode: 'single', modes: [
    { mode: 'free', available: true, providerAvailable: true, model: 'real-free-model' },
    { mode: 'paid', available: true, providerAvailable: true, model: 'real-paid-model' },
  ] },
});

function adapter(body: unknown = payload()) {
  const fetcher = vi.fn(async () => new Response(JSON.stringify(body)));
  return { fetcher, adapter: new SovereignProductionAdapter(fetcher, { enabled: true,
    deploymentMode: 'sovereign-agent-backend', agentApiUrl: 'https://agent.example.test', ready: true, reason: 'ready' }) };
}

describe('live control surface readbacks', () => {
  it('reads the exact job with cookies and does not invent balances, nodes or connectivity', async () => {
    const target = adapter();
    const result = await target.adapter.getControlSurface('agent-real');
    expect(target.fetcher.mock.calls[0]).toMatchObject(['https://agent.example.test/api/user/agent/control-surface?jobId=agent-real',
      { method: 'GET', credentials: 'include', cache: 'no-store' }]);
    expect(result.agents[0].status).toBe('BLOCKED');
    expect(result.integrations[0].status).toBe('defined_not_run');
    expect(result.credits).toMatchObject({ credits: 1250, providerFundedCredits: 1100 });
  });

  it.each(['wrong-job', 'invalid-balance', 'invalid-timestamp', 'unbound-agent', 'false-paid'])('rejects %s instead of showing a fabricated successful projection', async (invalid) => {
    const body = payload();
    if (invalid === 'wrong-job') body.jobId = 'agent-other';
    if (invalid === 'invalid-balance') body.credits.providerFundedCredits = 1300;
    if (invalid === 'invalid-timestamp') body.observedAt = 'not-a-server-timestamp';
    if (invalid === 'unbound-agent') body.agents[0].jobId = 'agent-other';
    if (invalid === 'false-paid') body.credits.providerFundedCredits = 0;
    await expect(adapter(body).adapter.getControlSurface('agent-real')).rejects.toThrow(/readback/i);
  });

  it('shows unavailable credits without substituting a zero balance', async () => {
    const body = { ...payload(), credits: { readbackState: 'unavailable', creditStateVerified: false, blocker: 'credit_state_verification_failed' } };
    body.routing.modes[1].available = false;
    const result = await adapter(body).adapter.getControlSurface('agent-real');
    render(<ChatSurface messages={[]} controlReadback={result} />);
    expect(screen.getByText(/credit_state_verification_failed/)).toBeVisible();
    expect(screen.queryByText(/0 ACCOUNT CREDITS/)).toBeNull();
    expect(screen.getByRole('option', { name: /Paid/ })).toBeDisabled();
  });

  it('renders real agent/task identities and integration blockers with readback provenance', async () => {
    const result = await adapter().adapter.getControlSurface('agent-real');
    const { unmount } = render(<SkillRegistryDrawer isOpen onClose={vi.fn()} agents={result.agents} observedAt={result.observedAt} />);
    await waitFor(() => expect(screen.getByText('free_single_agent')).toBeVisible());
    expect(screen.getByText(/task-real/)).toBeVisible();
    expect(screen.getByText(/BLOCKED/)).toBeVisible();
    expect(screen.getByText(/Persisted task state: RUNNING/)).toBeVisible();
    unmount();
    render(<IntegrationModal isOpen onClose={vi.fn()} integrations={result.integrations} observedAt={result.observedAt} />);
    await waitFor(() => expect(screen.getByText('Cloudflare R2')).toBeVisible());
    expect(screen.getByText('provider_head_canary_not_executed')).toBeVisible();
    expect(screen.getByText(/defined_not_run/)).toBeVisible();
    expect(screen.getByText('a'.repeat(64))).toBeVisible();
  });

  it('offers explicitly funded Paid execution separately from free and displays verified account credits', async () => {
    const result = await adapter().adapter.getControlSurface('agent-real');
    const selectMode = vi.fn();
    render(<ChatSurface messages={[]} controlReadback={result} onExecutionModeChange={selectMode} />);
    expect(screen.getByText(/1,250 ACCOUNT CREDITS/)).toBeVisible();
    expect(screen.getByText(/1,100 PROVIDER-FUNDED/)).toBeVisible();
    expect(screen.getByRole('option', { name: /Paid/ })).not.toBeDisabled();
    fireEvent.change(screen.getByRole('combobox', { name: 'ROUTE' }), { target: { value: 'paid' } });
    expect(selectMode).toHaveBeenCalledWith('paid');
    expect(screen.getByText(/No credit deduction and no automatic switch to Paid/)).toBeVisible();
  });

  it('shows refresh failures in both panels while preserving the last observed data as stale', async () => {
    const body = payload();
    const { unmount } = render(<SkillRegistryDrawer isOpen onClose={vi.fn()} agents={body.agents} readbackError="HTTP 503" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/HTTP 503/);
    await waitFor(() => expect(screen.getByText(/LAST OBSERVED/)).toBeVisible());
    unmount();
    render(<IntegrationModal isOpen onClose={vi.fn()} integrations={body.integrations} readbackError="HTTP 503" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/HTTP 503/);
  });
});
