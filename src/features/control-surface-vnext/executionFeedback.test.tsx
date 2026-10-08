import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { SovereignAdapterProvider } from './adapter/context';
import { SovereignProductionAdapter } from './adapter/repository-bound-adapter';
import { ChatSurface } from './components/ChatSurface/ChatSurface';
import { NeuralLoadMonitor } from './components/RuntimeMonitor/NeuralLoadMonitor';
import { useSovereignJob } from './hooks/useSovereignJob';

function Feedback() {
  const { job, abort, isAborting, abortError } = useSovereignJob('agent-feedback');
  return <ChatSurface messages={[]} jobPhase={job?.phase ?? 'IDLE'} onOpenToolchain={() => {}} onOpenSkills={() => {}} onOpenIntegrations={() => {}}
    onAbortJob={() => { void abort().catch(() => undefined); }} isAborting={isAborting} abortError={abortError?.message} />;
}

describe('execution feedback', () => {
  it('keeps the backend phase authoritative after an accepted abort request', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    let reads = 0;
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method !== 'POST') reads += 1;
      return new Response(JSON.stringify({ job: {
        jobId: 'agent-feedback', status: 'running', events: [], changedFiles: [],
        workspaceId: 'agent-feedback', executor: 'sovereign-local-runner',
      } }));
    });
    const adapter = new SovereignProductionAdapter(fetcher as typeof fetch, {
      enabled: true, deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://agent.example.test', ready: true, reason: 'ready',
    });
    render(<QueryClientProvider client={queryClient}><SovereignAdapterProvider adapter={adapter}><Feedback /></SovereignAdapterProvider></QueryClientProvider>);
    fireEvent.click(await screen.findByRole('button', { name: 'ABORT' }));
    await waitFor(() => expect(reads).toBeGreaterThan(1));
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true);
    expect(screen.getByText('EXECUTING')).toBeVisible();
    expect(screen.queryByText('CANCELLED')).not.toBeInTheDocument();
    queryClient.clear();
  });

  it('shows a rejected Abort instead of silently leaving the action unanswered', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const fetcher = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') return new Response(JSON.stringify({
        error: 'Sovereign-local cancellation is unsupported; no stop was confirmed.',
      }), { status: 409 });
      if (String(url).endsWith('/agent-feedback')) return new Response(JSON.stringify({ job: {
        jobId: 'agent-feedback', status: 'running', events: [], changedFiles: [],
        workspaceId: 'agent-feedback', executor: 'sovereign-local-runner',
      } }));
      return new Response('{}', { status: 404 });
    });
    const adapter = new SovereignProductionAdapter(fetcher as typeof fetch, {
      enabled: true, deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://agent.example.test', ready: true, reason: 'ready',
    });
    render(<QueryClientProvider client={queryClient}><SovereignAdapterProvider adapter={adapter}><Feedback /></SovereignAdapterProvider></QueryClientProvider>);
    fireEvent.click(await screen.findByRole('button', { name: 'ABORT' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Abort was not confirmed: Sovereign-local cancellation is unsupported; no stop was confirmed.');
    expect(screen.getByText('EXECUTING')).toBeVisible();
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    queryClient.clear();
  });

  it('prevents a second Abort request while the backend response is pending', () => {
    const abort = vi.fn();
    render(<ChatSurface messages={[]} jobPhase="EXECUTING" isAborting onAbortJob={abort} onOpenToolchain={() => {}} onOpenSkills={() => {}} onOpenIntegrations={() => {}} />);
    const button = screen.getByRole('button', { name: 'REQUESTING…' });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(abort).not.toHaveBeenCalled();
  });

  it('keeps Free and Paid unavailable until live route and account readback arrives', () => {
    render(<ChatSurface messages={[]} onOpenToolchain={() => {}} onOpenSkills={() => {}} onOpenIntegrations={() => {}} />);
    fireEvent.click(screen.getByText(/Mission controls/));
    expect(screen.getByRole('combobox', { name: 'ROUTE' })).toHaveValue('free');
    expect(screen.getByRole('option', { name: 'Sovereign · Free' })).toBeDisabled();
    expect(screen.getByRole('option', { name: 'Sovereign · Paid' })).toBeDisabled();
    expect(screen.queryByRole('option', { name: /Medium · Paid/ })).toBeNull();
    expect(screen.queryByRole('option', { name: /High · Paid/ })).toBeNull();
    expect(screen.queryByText('SWARM · OPT-IN')).toBeNull();
  });

  it('does not imply measured percentage progress from a running phase', () => {
    const { container } = render(<NeuralLoadMonitor phase="EXECUTING" />);
    expect(screen.getByText(/completion percentage is unavailable/i)).toBeVisible();
    expect(container.textContent).not.toMatch(/\d+%/);
  });
});
