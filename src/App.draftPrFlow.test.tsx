import React from 'react';
import { Provider } from 'react-redux';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { store } from './store';

const TEST_GITHUB_ACCESS = 'fixture-only';

const agent = vi.hoisted(() => ({
  listJobs: vi.fn(),
  startJob: vi.fn(),
  startToolchainJob: vi.fn(),
  getJob: vi.fn(),
  cancelJob: vi.fn(),
  runJanitor: vi.fn(),
  prepareDraftPr: vi.fn(),
  createDraftPr: vi.fn(),
}));

vi.mock('./features/product/runtime/sovereignAgentClient', () => ({
  createSovereignAgentClient: () => agent,
}));

vi.mock('./features/product/runtime/sovereignAgentRuntime', () => ({
  resolveSovereignAgentConfig: () => ({
    enabled: true,
    ready: true,
    reason: 'ready',
    agentApiUrl: 'https://agent.example.test',
  }),
  createSovereignAgentIdleSnapshot: () => ({ status: 'idle', changedFiles: [], events: [] }),
  summarizeSovereignAgentJob: (job: { status: string }) => `status=${job.status}`,
}));

vi.mock('./features/product/containers/BuilderContainer', () => ({
  BuilderContainer: (props: any) => (
    <section>
      <div data-testid="flow-job-id">{props.agentJob?.jobId || 'none'}</div>
      <div data-testid="flow-job-status">{props.agentJob?.status || 'none'}</div>
      <div data-testid="flow-pr-url">{props.agentJob?.draftPrUrl || 'none'}</div>
      <div data-testid="flow-repo-ready">{String(props.repoReady)}</div>
      <div data-testid="flow-repo-reason">{props.repoReason}</div>
      <button
        type="button"
        onClick={() => {
          void props.onPublishDraftPr({
            repoUrl: 'https://github.com/acme/repo',
            branch: 'main',
            mission: 'Update README',
            changes: [],
            confirmed: true,
            githubAccessToken: TEST_GITHUB_ACCESS,
          }).catch(() => undefined);
        }}
      >Publish existing</button>
      <button
        type="button"
        onClick={() => {
          void props.onPublishDraftPr({
            repoUrl: 'https://github.com/acme/repo',
            branch: 'main',
            mission: 'Update README',
            changes: [{ path: 'README.md', content: '# Updated\n', baseContent: '# Original\n' }],
            confirmed: true,
            githubAccessToken: TEST_GITHUB_ACCESS,
          }).catch(() => undefined);
        }}
      >Publish staged</button>
    </section>
  ),
}));

function snapshot(overrides: Record<string, unknown> = {}) {
  return {
    jobId: 'job-1',
    workspaceId: 'job-1',
    runtimeId: 'job-1',
    status: 'running',
    repoUrl: 'https://github.com/acme/repo',
    branch: 'main',
    changedFiles: ['README.md'],
    events: [],
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('App Draft-PR runtime flow', () => {
  it('retries persisted-job recovery after a later authenticated session exists', async () => {
    vi.useFakeTimers();
    agent.listJobs
      .mockRejectedValueOnce(new Error('session missing'))
      .mockResolvedValueOnce([snapshot({ status: 'completed' })]);

    render(<Provider store={store}><App /></Provider>);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId('flow-job-id')).toHaveTextContent('none');

    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

    expect(screen.getByTestId('flow-job-id')).toHaveTextContent('job-1');
    expect(agent.listJobs).toHaveBeenCalledTimes(2);
  });

  it('does not mark a failed persisted job as repository-ready', async () => {
    agent.listJobs.mockResolvedValue([snapshot({
      status: 'failed',
      lastError: 'Clone fehlgeschlagen',
    })]);

    render(<Provider store={store}><App /></Provider>);

    await waitFor(() => expect(screen.getByTestId('flow-job-status')).toHaveTextContent('failed'));
    expect(screen.getByTestId('flow-repo-ready')).toHaveTextContent('false');
    expect(screen.getByTestId('flow-repo-reason')).toHaveTextContent('GitHub-URL direkt im Chat einfügen.');
  });

  it('preserves the final runtime snapshot status instead of inventing completed state', async () => {
    agent.listJobs.mockResolvedValue([snapshot()]);
    agent.prepareDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-1',
      draftPrPreparation: { allowed: true, decision: 'ready', blockers: [] },
    });
    agent.createDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-1',
      draftPrCreate: {
        allowed: true,
        status: 'created',
        prUrl: 'https://github.com/acme/repo/pull/10',
      },
    });
    agent.getJob.mockResolvedValue(snapshot({
      status: 'validating',
      draftPrUrl: 'https://github.com/acme/repo/pull/10',
    }));

    render(<Provider store={store}><App /></Provider>);
    await waitFor(() => expect(screen.getByTestId('flow-job-id')).toHaveTextContent('job-1'));
    fireEvent.click(screen.getByRole('button', { name: 'Publish existing' }));

    await waitFor(() => expect(screen.getByTestId('flow-pr-url')).toHaveTextContent('/pull/10'));
    expect(screen.getByTestId('flow-job-status')).toHaveTextContent('validating');
  });

  it('restores a persisted job and continues the same job to the confirmed PR URL', async () => {
    agent.listJobs.mockResolvedValue([snapshot()]);
    agent.prepareDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-1',
      draftPrPreparation: { allowed: true, decision: 'ready', blockers: [] },
    });
    agent.createDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-1',
      draftPrCreate: {
        allowed: true,
        status: 'created',
        prUrl: 'https://github.com/acme/repo/pull/10',
      },
    });
    agent.getJob.mockResolvedValue(snapshot({
      status: 'completed',
      draftPrUrl: 'https://github.com/acme/repo/pull/10',
    }));

    render(<Provider store={store}><App /></Provider>);
    await waitFor(() => expect(screen.getByTestId('flow-job-id')).toHaveTextContent('job-1'));
    fireEvent.click(screen.getByRole('button', { name: 'Publish existing' }));

    // wait for the UI to update and assert the visible PR path
    await waitFor(() => expect(screen.getByTestId('flow-pr-url')).toHaveTextContent('/pull/10'));

    expect(agent.startJob).not.toHaveBeenCalled();
    expect(agent.prepareDraftPr).toHaveBeenCalledWith('job-1');

    expect(agent.createDraftPr).toHaveBeenCalled();
    expect(agent.createDraftPr.mock.calls[0]).toEqual(['job-1', TEST_GITHUB_ACCESS]);

    expect(agent.getJob).toHaveBeenCalledWith('job-1');
  });

  it('stages confirmed content once before prepare, create and final reload', async () => {
    agent.listJobs.mockResolvedValue([]);
    agent.startToolchainJob.mockResolvedValue(snapshot({ jobId: 'job-staged', workspaceId: 'job-staged', runtimeId: 'job-staged' }));
    agent.prepareDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-staged',
      draftPrPreparation: { allowed: true, decision: 'ready', blockers: [] },
    });
    agent.createDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-staged',
      draftPrCreate: {
        allowed: true,
        status: 'created',
        prUrl: 'https://github.com/acme/repo/pull/11',
      },
    });
    agent.getJob.mockResolvedValue(snapshot({
      jobId: 'job-staged',
      workspaceId: 'job-staged',
      runtimeId: 'job-staged',
      status: 'completed',
      draftPrUrl: 'https://github.com/acme/repo/pull/11',
    }));

    render(<Provider store={store}><App /></Provider>);
    fireEvent.click(screen.getByRole('button', { name: 'Publish staged' }));

    // wait for the UI to reflect the PR URL
    const prUrlEl = await screen.findByTestId('flow-pr-url');
    expect(prUrlEl).toHaveTextContent('/pull/11');

    expect(agent.startToolchainJob).toHaveBeenCalledTimes(1);
    expect(agent.startToolchainJob).toHaveBeenCalledWith(expect.objectContaining({
      repoUrl: 'https://github.com/acme/repo',
      cloneRepo: true,
      provisionWorkspace: true,
      stagedFiles: [{ path: 'README.md', content: '# Updated\n', baseContent: '# Original\n' }],
      githubAccessToken: TEST_GITHUB_ACCESS,
    }));
    expect(agent.prepareDraftPr).toHaveBeenCalledWith('job-staged');

    expect(agent.createDraftPr).toHaveBeenCalled();
    expect(agent.createDraftPr.mock.calls[0]).toEqual(['job-staged', TEST_GITHUB_ACCESS]);

    expect(agent.getJob).toHaveBeenCalledWith('job-staged');
  });
});
