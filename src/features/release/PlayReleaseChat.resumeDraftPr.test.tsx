import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PlayReleaseChat } from './PlayReleaseChat';

const runtime = vi.hoisted(() => ({
  catalog: vi.fn(),
  health: vi.fn(),
  reply: vi.fn(),
  parseRepo: vi.fn(),
  interpret: vi.fn(),
  fallback: vi.fn(),
  evaluateInputPolicy: vi.fn(),
  ensureGuestSession: vi.fn(),
  refreshUser: vi.fn(),
  logout: vi.fn(),
  loginWithGitHub: vi.fn(),
  initiateGitHubOAuth: vi.fn(),
  agentStart: vi.fn(),
  agentGet: vi.fn(),
  prepareDraftPr: vi.fn(),
  createDraftPr: vi.fn(),
}));

vi.mock('../product/runtime/devChatWorkerBridge', () => ({
  DEV_CHAT_WORKER_DEFAULT_MODEL: 'sovereign-fast',
  fetchSovereignLlmRouteCatalog: runtime.catalog,
  fetchDevChatWorkerHealth: runtime.health,
  fetchDevChatWorkerReply: runtime.reply,
  parseDevChatGithubUrl: runtime.parseRepo,
}));

vi.mock('../product/runtime/sovereignDirectLlmIntentRuntime', () => ({
  fetchSovereignDirectLlmInterpretation: runtime.interpret,
}));

vi.mock('../product/runtime/repositoryActionFallback', () => ({
  deriveRepositoryActionFallback: runtime.fallback,
}));

vi.mock('../product/runtime/sovereignAgentClient', () => ({
  createSovereignAgentClient: () => ({
    startRepositoryExecution: runtime.agentStart,
    getJob: runtime.agentGet,
    prepareDraftPr: runtime.prepareDraftPr,
    createDraftPr: runtime.createDraftPr,
  }),
}));

vi.mock('../product/runtime/sovereignAgentRuntime', () => ({
  resolveSovereignAgentConfig: () => ({
    enabled: true,
    deploymentMode: 'sovereign-agent-backend',
    agentApiUrl: 'https://backend.example.test',
    ready: true,
    reason: 'ready',
  }),
  isSovereignAgentTerminalStatus: (status: string) => ['blocked', 'failed', 'completed', 'cleaned'].includes(status),
  summarizeSovereignAgentJob: (job: { status: string; draftPrUrl?: string; lastError?: string }) => (
    job.draftPrUrl ? `Draft PR ${job.draftPrUrl}` : job.lastError || `Agent ${job.status}`
  ),
}));

vi.mock('../product/runtime/secureInputGuard', () => ({
  evaluateInputPolicy: runtime.evaluateInputPolicy,
}));

vi.mock('../github/githubOAuthLogin', () => ({
  initiateGitHubOAuth: runtime.initiateGitHubOAuth,
}));

vi.mock('../product/components/GitHubAccessCard', () => ({
  GitHubAccessCard: () => <div role="group" aria-label="GitHub-Zugang" />,
}));

vi.mock('../user/useUserStore', () => ({
  useUserStore: () => ({
    user: {
      id: 'release-user',
      email: 'release@example.test',
      displayName: 'Release User',
      role: 'user',
      credits: 100,
      subscriptionStatus: 'free',
      isBanned: false,
      createdAt: 1,
    },
    ensureGuestSession: runtime.ensureGuestSession,
    refreshUser: runtime.refreshUser,
    logout: runtime.logout,
    loginWithGitHub: runtime.loginWithGitHub,
  }),
}));

const TARGET = {
  owner: 'acme',
  repo: 'repo',
  branch: 'main',
  path: '',
  name: 'repo',
  repoUrl: 'https://github.com/acme/repo',
};

const RELEASE_TARGET = {
  repoUrl: TARGET.repoUrl,
  branch: TARGET.branch,
  label: `${TARGET.owner}/${TARGET.repo}`,
};

function completedJob(jobId: string) {
  return {
    jobId,
    workspaceId: `ws-${jobId}`,
    runtimeId: `run-${jobId}`,
    status: 'completed',
    repoUrl: TARGET.repoUrl,
    branch: 'main',
    changedFiles: ['README.md'],
    events: [],
  };
}

function runningJob(jobId: string) {
  return {
    jobId,
    workspaceId: `ws-${jobId}`,
    runtimeId: `run-${jobId}`,
    status: 'running',
    repoUrl: TARGET.repoUrl,
    branch: 'main',
    changedFiles: [],
    events: [],
  };
}

function draftPreparation(jobId: string) {
  return {
    ok: true,
    jobId,
    draftPrPreparation: {
      allowed: true,
      decision: 'ready',
      canCreateDraftPr: true,
      blockers: [],
    },
  };
}

function draftCreation(jobId: string) {
  return {
    ok: true,
    jobId,
    draftPrCreate: {
      allowed: true,
      status: 'created',
      prUrl: 'https://github.com/acme/repo/pull/42',
      headSha: 'a'.repeat(40),
      publishedHeadSha: 'a'.repeat(40),
      readbackHeadSha: 'a'.repeat(40),
      prNumber: 42,
      draftVerified: true,
      prStateVerified: 'open',
      headBranch: 'sovereign/agent-42',
      baseBranch: 'main',
      readbackVerified: true,
      checksReadbackVerified: true,
      ciState: 'pending',
      checkRunCount: 1,
      checksPendingCount: 1,
      checksSuccessCount: 0,
      checksFailureCount: 0,
      statusContextCount: 0,
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
  runtime.catalog.mockResolvedValue([]);
  runtime.health.mockResolvedValue({ ok: true, route: '/health/ready', status: 200 });
  runtime.reply.mockResolvedValue({ ok: true, content: 'chat reply' });
  runtime.parseRepo.mockReturnValue(TARGET);
  runtime.fallback.mockReturnValue({ intent: 'draft_pr', actionTitle: 'README reparieren' });
  runtime.evaluateInputPolicy.mockReturnValue({ shouldBlock: false });
  runtime.ensureGuestSession.mockResolvedValue(undefined);
  runtime.refreshUser.mockResolvedValue(undefined);
  runtime.logout.mockResolvedValue(undefined);
  runtime.loginWithGitHub.mockResolvedValue(undefined);
  runtime.initiateGitHubOAuth.mockResolvedValue({ success: false, error: 'not used' });
});

describe('PlayReleaseChat Draft-PR runtime continuity', () => {
  it('keeps a clear repository action executable when the online intent interpreter fails', async () => {
    runtime.interpret.mockRejectedValue(new Error('intent route unavailable'));
    runtime.agentStart.mockResolvedValue(completedJob('job-fallback'));
    runtime.prepareDraftPr.mockResolvedValue(draftPreparation('job-fallback'));
    runtime.createDraftPr.mockResolvedValue(draftCreation('job-fallback'));

    render(<PlayReleaseChat />);
    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'Repariere die README und erstelle einen Draft PR: https://github.com/acme/repo' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));

    const start = await screen.findByRole('button', { name: 'Repository-Ausführung starten' });
    expect(runtime.interpret).toHaveBeenCalledOnce();
    expect(runtime.fallback).toHaveBeenCalled();
    expect(runtime.agentStart).not.toHaveBeenCalled();

    fireEvent.click(start);
    await waitFor(() => expect(runtime.agentStart).toHaveBeenCalledOnce());

    const publish = await screen.findByRole('button', { name: 'Draft PR erstellen' });
    fireEvent.click(publish);
    await waitFor(() => expect(runtime.prepareDraftPr).toHaveBeenCalledWith('job-fallback'));
    await waitFor(() => expect(runtime.createDraftPr).toHaveBeenCalledWith('job-fallback'));
    expect(await screen.findByText(/github\.com\/acme\/repo\/pull\/42/)).toBeDefined();
    expect(runtime.reply).not.toHaveBeenCalled();
  });

  it('restores one nonterminal repository job and follows that same job instead of starting a duplicate', async () => {
    window.sessionStorage.setItem('sovereign.play-release.active-repository-action.v1', JSON.stringify({
      schemaVersion: 1,
      jobId: 'job-resume',
      text: 'Repariere README und erstelle Draft PR',
      actionTitle: 'README reparieren',
      intent: 'draft_pr',
      target: RELEASE_TARGET,
    }));
    runtime.agentGet
      .mockResolvedValueOnce(runningJob('job-resume'))
      .mockResolvedValueOnce(completedJob('job-resume'));

    render(<PlayReleaseChat />);

    const follow = await screen.findByRole('button', { name: 'Ausführung weiter verfolgen' });
    expect(runtime.agentStart).not.toHaveBeenCalled();
    fireEvent.click(follow);

    await screen.findByRole('button', { name: 'Draft PR erstellen' });
    expect(runtime.agentGet).toHaveBeenCalledWith('job-resume');
    expect(runtime.agentStart).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem('sovereign.play-release.active-repository-action.v1')).toContain('job-resume');
  });
});
