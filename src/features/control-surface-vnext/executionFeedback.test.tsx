import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
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
  it('shows a rejected Abort instead of silently leaving the action unanswered', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const fetcher = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') return new Response(JSON.stringify({
        error: 'Agent Zero cancellation is unsupported; no stop was confirmed.',
      }), { status: 409 });
      if (String(url).endsWith('/agent-feedback')) return new Response(JSON.stringify({ job: {
        jobId: 'agent-feedback', status: 'running', events: [], changedFiles: [],
        workspaceId: 'agent-feedback', externalRef: 'agent-zero-a2a:task-feedback',
      } }));
      return new Response('{}', { status: 404 });
    });
    const adapter = new SovereignProductionAdapter(fetcher as typeof fetch, {
      enabled: true, deploymentMode: 'sovereign-agent-backend',
      agentApiUrl: 'https://agent.example.test', ready: true, reason: 'ready',
    });
    render(<QueryClientProvider client={queryClient}><SovereignAdapterProvider adapter={adapter}><Feedback /></SovereignAdapterProvider></QueryClientProvider>);
    fireEvent.click(await screen.findByRole('button', { name: 'ABORT' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Abort was not confirmed: Agent Zero cancellation is unsupported; no stop was confirmed.');
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

  it('offers the requested route labels without pretending unavailable paid execution is connected', () => {
    render(<ChatSurface messages={[]} onOpenToolchain={() => {}} onOpenSkills={() => {}} onOpenIntegrations={() => {}} />);
    expect(screen.getByRole('combobox', { name: 'ROUTE' })).toHaveValue('low');
    expect(screen.getByRole('option', { name: 'Low · Free' })).not.toBeDisabled();
    expect(screen.getByRole('option', { name: /Medium · Paid/ })).toBeDisabled();
    expect(screen.getByRole('option', { name: /High · Paid/ })).toBeDisabled();
    expect(screen.queryByText('SWARM · OPT-IN')).toBeNull();
  });

  it('does not imply measured percentage progress from a running phase', () => {
    const { container } = render(<NeuralLoadMonitor phase="EXECUTING" />);
    expect(screen.getByText(/completion percentage is unavailable/)).toBeVisible();
    expect(container.textContent).not.toMatch(/\d+%/);
  });
});
