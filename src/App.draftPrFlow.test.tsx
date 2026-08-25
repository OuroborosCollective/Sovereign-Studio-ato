import React from 'react';
import { Provider } from 'react-redux';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { store } from './store';

const agent = vi.hoisted(() => ({
  listJobs: vi.fn(),
  startJob: vi.fn(),
  startToolchainJob: vi.fn(),
  getJob: vi.fn(),
  getProjections: vi.fn(),
  getEvidenceAnchors: vi.fn(async () => []),
  getDesktopFrame: vi.fn(),
  cancelJob: vi.fn(),
  runJanitor: vi.fn(),
  prepareDraftPr: vi.fn(),
  createDraftPr: vi.fn(),
}));

const memory = vi.hoisted(() => ({
  searchReusableMemory: vi.fn(),
  reusableMemoryContext: vi.fn(),
}));

vi.mock('./features/knowledge/knowledgeApi', () => ({
  searchReusableMemory: memory.searchReusableMemory,
  reusableMemoryContext: memory.reusableMemoryContext,
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
  maskSovereignAgentSensitiveText: (value: string) => value,
  summarizeSovereignAgentJob: (job: { status: string }) => `status=${job.status}`,
  isSovereignAgentTerminalStatus: (status: string) => ['blocked', 'failed', 'completed', 'cleaned'].includes(status),
}));

vi.mock('./features/product/containers/BuilderContainer', () => ({
  BuilderContainer: (props: any) => (
    <section>
      <div data-testid="flow-job-id">{props.agentJob?.jobId || 'none'}</div>
      <div data-testid="flow-job-status">{props.agentJob?.status || 'none'}</div>
      <div data-testid="flow-pr-url">{props.agentJob?.draftPrUrl || 'none'}</div>
      <div data-testid="flow-repo-ready">{String(props.repoReady)}</div>
      <div data-testid="flow-repo-reason">{props.repoReason}</div>
      <div data-testid="flow-frame-hash">{props.desktopFrame?.frameHash || 'none'}</div>
      <button
        type="button"
        onClick={() => {
          void props.onStartAgent('Switch to job B', {
            repoUrl: 'https://github.com/acme/repo',
            branch: 'main',
          });
        }}
      >Switch job</button>
      <button
        type="button"
        onClick={() => {
          void props.onPublishDraftPr({
            repoUrl: 'https://github.com/acme/repo',
            branch: 'main',
            mission: 'Update README',
            changes: [],
            confirmed: true,
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

function verifiedDraftPrCreate(jobId: string, prNumber: number) {
  const sha = 'a'.repeat(40);
  return {
    ok: true,
    jobId,
    draftPrCreate: {
      allowed: true,
      status: 'created',
      prUrl: `https://github.com/acme/repo/pull/${prNumber}`,
      headSha: sha,
      publishedHeadSha: sha,
      readbackHeadSha: sha,
      prNumber,
      draftVerified: true,
      prStateVerified: 'open',
      headBranch: `sovereign/${jobId}`,
      baseBranch: 'main',
      readbackVerified: true,
      checksReadbackVerified: true,
      ciState: 'pending',
      checkRunCount: 2,
      checksPendingCount: 1,
      checksSuccessCount: 1,
      checksFailureCount: 0,
      statusContextCount: 0,
    },
  };
}

beforeEach(() => {
  memory.searchReusableMemory.mockResolvedValue([]);
  memory.reusableMemoryContext.mockReturnValue('');
  agent.getProjections.mockResolvedValue([]);
  agent.getDesktopFrame.mockRejectedValue(new Error('desktop frame unavailable'));
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
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

  it('refreshes projections once for a terminal job and does not keep polling', async () => {
    vi.useFakeTimers();
    agent.listJobs.mockResolvedValue([snapshot({ status: 'completed' })]);

    render(<Provider store={store}><App /></Provider>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(screen.getByTestId('flow-job-status')).toHaveTextContent('completed');
    expect(agent.getProjections).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(agent.getProjections).toHaveBeenCalledTimes(1);
  });

  it('revokes and clears job A desktop evidence before job B can render', async () => {
    const jobAHash = 'a'.repeat(64);
    const jobBHash = 'b'.repeat(64);
    const createObjectURL = vi.fn()
      .mockReturnValueOnce('blob:job-a')
      .mockReturnValueOnce('blob:job-b');
    const revokeObjectURL = vi.fn();
    class TestURL extends URL {}
    Object.defineProperty(TestURL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(TestURL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
    vi.stubGlobal('URL', TestURL);

    let resolveJobBFrame: ((value: { blob: Blob; frameHash: string; observedAt: number }) => void) | undefined;
    const pendingJobBFrame = new Promise<{ blob: Blob; frameHash: string; observedAt: number }>((resolve) => {
      resolveJobBFrame = resolve;
    });
    agent.listJobs.mockResolvedValue([snapshot({
      jobId: 'job-a',
      workspaceId: 'job-a',
      runtimeId: 'job-a',
      status: 'completed',
    })]);
    agent.getDesktopFrame.mockImplementation(async (jobId: string) => {
      if (jobId === 'job-a') {
        return { blob: new Blob(['job-a'], { type: 'image/png' }), frameHash: jobAHash, observedAt: 1 };
      }
      return pendingJobBFrame;
    });
    agent.startJob.mockResolvedValue(snapshot({
      jobId: 'job-b',
      workspaceId: 'job-b',
      runtimeId: 'job-b',
      status: 'running',
    }));

    render(<Provider store={store}><App /></Provider>);
    await waitFor(() => expect(screen.getByTestId('flow-frame-hash')).toHaveTextContent(jobAHash));

    fireEvent.click(screen.getByRole('button', { name: 'Switch job' }));
    await waitFor(() => expect(screen.getByTestId('flow-job-id')).toHaveTextContent('job-b'));
    await waitFor(() => expect(agent.getDesktopFrame).toHaveBeenCalledWith('job-b'));
    expect(screen.getByTestId('flow-frame-hash')).toHaveTextContent('none');
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:job-a');

    await act(async () => {
      resolveJobBFrame?.({
        blob: new Blob(['job-b'], { type: 'image/png' }),
        frameHash: jobBHash,
        observedAt: 2,
      });
      await pendingJobBFrame;
    });
    await waitFor(() => expect(screen.getByTestId('flow-frame-hash')).toHaveTextContent(jobBHash));
  });

  it('does not mark a failed persisted job as repository-ready', async () => {
    agent.listJobs.mockResolvedValue([snapshot({
      status: 'failed',
      lastError: 'Clone fehlgeschlagen',
    })]);

    render(<Provider store={store}><App /></Provider>);

    await waitFor(() => expect(screen.getByTestId('flow-job-status')).toHaveTextContent('failed'));
    expect(screen.getByTestId('flow-repo-ready')).toHaveTextContent('false');
    expect(screen.getByTestId('flow-repo-reason')).toHaveTextContent('Noch kein Repository an den Workspace-Monitor gebunden.');
  });

  it('preserves the final runtime snapshot status instead of inventing completed state', async () => {
    agent.listJobs.mockResolvedValue([snapshot()]);
    agent.prepareDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-1',
      draftPrPreparation: { allowed: true, decision: 'ready', blockers: [] },
    });
    agent.createDraftPr.mockResolvedValue(verifiedDraftPrCreate('job-1', 10));
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

  it('restores a persisted job and continues the same job to the verified Draft PR URL', async () => {
    agent.listJobs.mockResolvedValue([snapshot()]);
    agent.prepareDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-1',
      draftPrPreparation: { allowed: true, decision: 'ready', blockers: [] },
    });
    agent.createDraftPr.mockResolvedValue(verifiedDraftPrCreate('job-1', 10));
    agent.getJob.mockResolvedValue(snapshot({
      status: 'completed',
      draftPrUrl: 'https://github.com/acme/repo/pull/10',
    }));

    render(<Provider store={store}><App /></Provider>);
    await waitFor(() => expect(screen.getByTestId('flow-job-id')).toHaveTextContent('job-1'));
    fireEvent.click(screen.getByRole('button', { name: 'Publish existing' }));

    await waitFor(() => expect(screen.getByTestId('flow-pr-url')).toHaveTextContent('/pull/10'));

    expect(agent.startJob).not.toHaveBeenCalled();
    expect(agent.prepareDraftPr).toHaveBeenCalledWith('job-1', undefined);
    expect(agent.createDraftPr).toHaveBeenCalledWith('job-1', undefined);
    expect(agent.getJob).toHaveBeenCalledWith('job-1');
  });

  it('stages confirmed content once before prepare, verified create and final reload', async () => {
    agent.listJobs.mockResolvedValue([]);
    agent.startToolchainJob.mockResolvedValue(snapshot({ jobId: 'job-staged', workspaceId: 'job-staged', runtimeId: 'job-staged' }));
    agent.prepareDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-staged',
      draftPrPreparation: { allowed: true, decision: 'ready', blockers: [] },
    });
    agent.createDraftPr.mockResolvedValue(verifiedDraftPrCreate('job-staged', 11));
    agent.getJob.mockResolvedValue(snapshot({
      jobId: 'job-staged',
      workspaceId: 'job-staged',
      runtimeId: 'job-staged',
      status: 'completed',
      draftPrUrl: 'https://github.com/acme/repo/pull/11',
    }));

    render(<Provider store={store}><App /></Provider>);
    fireEvent.click(screen.getByRole('button', { name: 'Publish staged' }));

    await waitFor(() => expect(screen.getByTestId('flow-pr-url')).toHaveTextContent('/pull/11'));

    expect(memory.searchReusableMemory).toHaveBeenCalledWith('Update README', 6);
    expect(agent.startToolchainJob).toHaveBeenCalledTimes(1);
    expect(agent.startToolchainJob).toHaveBeenCalledWith(expect.objectContaining({
      repoUrl: 'https://github.com/acme/repo',
      evidenceText: 'Update README',
      cloneRepo: true,
      provisionWorkspace: true,
      stagedFiles: [{ path: 'README.md', content: '# Updated\n', baseContent: '# Original\n' }],
    }));
    expect(agent.prepareDraftPr).toHaveBeenCalledWith('job-staged', undefined);
    expect(agent.createDraftPr).toHaveBeenCalledWith('job-staged', undefined);
    expect(agent.getJob).toHaveBeenCalledWith('job-staged');
  });
});
