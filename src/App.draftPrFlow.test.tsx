import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PlayReleaseChat } from './features/release/PlayReleaseChat';

const runtime = vi.hoisted(() => ({
  catalog: vi.fn(),
  health: vi.fn(),
  reply: vi.fn(),
  interpret: vi.fn(),
  parseRepo: vi.fn(),
  evaluateInputPolicy: vi.fn(),
  refreshUser: vi.fn(),
  logout: vi.fn(),
  agentStart: vi.fn(),
  agentGet: vi.fn(),
  prepareDraftPr: vi.fn(),
  createDraftPr: vi.fn(),
  initiateGitHubOAuth: vi.fn(),
  loginWithGitHub: vi.fn(),
}));

vi.mock('./features/product/runtime/devChatWorkerBridge', () => ({
  DEV_CHAT_WORKER_DEFAULT_MODEL: 'sovereign-fast',
  fetchSovereignLlmRouteCatalog: runtime.catalog,
  fetchDevChatWorkerHealth: runtime.health,
  fetchDevChatWorkerReply: runtime.reply,
  parseDevChatGithubUrl: runtime.parseRepo,
}));

vi.mock('./features/product/runtime/sovereignDirectLlmIntentRuntime', () => ({
  fetchSovereignDirectLlmInterpretation: runtime.interpret,
}));

vi.mock('./features/product/runtime/sovereignAgentClient', () => ({
  createSovereignAgentClient: () => ({
    startRepositoryExecution: runtime.agentStart,
    getJob: runtime.agentGet,
    prepareDraftPr: runtime.prepareDraftPr,
    createDraftPr: runtime.createDraftPr,
  }),
}));

vi.mock('./features/product/runtime/sovereignAgentRuntime', () => ({
  resolveSovereignAgentConfig: () => ({
    enabled: true,
    deploymentMode: 'sovereign-agent-backend',
    agentApiUrl: 'https://backend.example.test',
    ready: true,
    reason: 'ready',
  }),
  isSovereignAgentTerminalStatus: (status: string) => ['blocked', 'failed', 'completed', 'cleaned'].includes(status),
  summarizeSovereignAgentJob: (job: { status: string; draftPrUrl?: string }) => job.draftPrUrl
    ? `Draft PR ${job.draftPrUrl}`
    : `Agent ${job.status}`,
}));

vi.mock('./features/product/runtime/secureInputGuard', () => ({
  evaluateInputPolicy: runtime.evaluateInputPolicy,
}));

vi.mock('./features/github/githubOAuthLogin', () => ({
  initiateGitHubOAuth: runtime.initiateGitHubOAuth,
}));

vi.mock('./features/user/useUserStore', () => ({
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
    refreshUser: runtime.refreshUser,
    logout: runtime.logout,
    isLoading: false,
    error: null,
    clearError: vi.fn(),
    login: vi.fn(),
    loginWithGitHub: runtime.loginWithGitHub,
    register: vi.fn(),
  }),
}));

const FREE_ROUTE = {
  id: 'free-route-1',
  defaultModelId: 'free-model-1',
  label: 'Free Revolver',
  provider: 'freellm',
  billingCategory: 'free' as const,
  priority: 1,
  enabled: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  runtime.catalog.mockResolvedValue([FREE_ROUTE]);
  runtime.health.mockResolvedValue({ ok: true, route: '/health/ready', status: 200 });
  runtime.reply.mockResolvedValue({
    ok: true,
    content: 'Antwort aus der aktuellen Sovereign LLM-Runtime.',
    route: '/api/llm/chat',
    fallbackUsed: false,
    preferredModel: 'free-route-1',
    actualModel: 'free-route-1',
  });
  runtime.interpret.mockResolvedValue({ ok: false, error: 'no repo context' });
  runtime.parseRepo.mockReturnValue(null);
  runtime.agentStart.mockReset();
  runtime.agentGet.mockReset();
  runtime.prepareDraftPr.mockReset();
  runtime.createDraftPr.mockReset();
  runtime.evaluateInputPolicy.mockReturnValue({ shouldBlock: false });
  runtime.refreshUser.mockResolvedValue(undefined);
  runtime.logout.mockResolvedValue(undefined);
  runtime.initiateGitHubOAuth.mockResolvedValue({ success: false, error: 'not used in this suite' });
  runtime.loginWithGitHub.mockResolvedValue(undefined);
});

describe('Play release chat runtime integration', () => {
  it('keeps the compact release menu, model picker and evidence-derived status cues visible', async () => {
    render(<PlayReleaseChat />);

    expect(screen.getByTestId('play-release-menu-frame')).toBeDefined();
    expect(screen.getByRole('button', { name: /Chat/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /GitHub/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /Modelle/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /Konto/ })).toBeDefined();
    expect(screen.getByLabelText('LLM Route')).toBeDefined();
    expect(screen.getByLabelText('Session bestätigt')).toBeDefined();
    expect(screen.getByLabelText('GitHub nicht verbunden')).toBeDefined();

    await waitFor(() => expect(screen.getByLabelText('LLM bereit')).toBeDefined());
    expect(screen.getByTestId('release-guide-mood')).toHaveTextContent('😊✨');

    fireEvent.click(screen.getByRole('button', { name: /GitHub/ }));
    expect(screen.getByText(/Noch kein Repository-Ziel im Chat gebunden/)).toBeDefined();
  });

  it('loads the authenticated current route catalog and labels automatic routing as server-authoritative', async () => {
    render(<PlayReleaseChat />);

    await waitFor(() => expect(runtime.catalog).toHaveBeenCalled());
    expect(screen.getByRole('option', { name: 'Auto · serverseitige Routenwahl' })).toBeDefined();
    expect(await screen.findByRole('option', { name: 'FREE · Free Revolver' })).toBeDefined();
    expect(screen.getByText('release@example.test')).toBeDefined();
  });

  it('connects GitHub only after an explicit visible OAuth consent action', async () => {
    runtime.initiateGitHubOAuth.mockResolvedValue({
      success: true,
      code: 'oauth-code',
      state: 'oauth-state',
      codeVerifier: 'pkce-verifier',
    });
    render(<PlayReleaseChat />);

    fireEvent.click(screen.getByRole('button', { name: /GitHub/ }));
    expect(runtime.initiateGitHubOAuth).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'GitHub sicher verbinden' }));

    await waitFor(() => expect(runtime.loginWithGitHub).toHaveBeenCalledWith({
      code: 'oauth-code',
      state: 'oauth-state',
      codeVerifier: 'pkce-verifier',
    }));
    expect(runtime.refreshUser).toHaveBeenCalled();
  });

  it('routes an explicit GitHub coding command through agent execution and verified Draft-PR readback', async () => {
    runtime.parseRepo.mockReturnValue({
      owner: 'acme',
      repo: 'repo',
      branch: 'main',
      path: '',
      name: 'repo',
      repoUrl: 'https://github.com/acme/repo',
    });
    runtime.interpret.mockResolvedValue({
      ok: true,
      interpretation: {
        mode: 'action',
        intent: 'draft_pr',
        actionDisposition: 'execute',
        assistantText: '',
        actionTitle: 'README aktualisieren',
        confidence: 0.98,
        language: 'de',
        model: 'free-route-1',
        fallbackUsed: false,
      },
    });
    runtime.agentStart.mockResolvedValue({
      jobId: 'job-release-1',
      workspaceId: 'ws-release-1',
      runtimeId: 'run-release-1',
      status: 'completed',
      repoUrl: 'https://github.com/acme/repo',
      branch: 'main',
      changedFiles: ['README.md'],
      events: [],
    });
    runtime.prepareDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-release-1',
      draftPrPreparation: {
        allowed: true,
        decision: 'ready',
        canCreateDraftPr: true,
        blockers: [],
      },
    });
    runtime.createDraftPr.mockResolvedValue({
      ok: true,
      jobId: 'job-release-1',
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
        headBranch: 'sovereign/release-42',
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
    });

    render(<PlayReleaseChat />);
    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'Ändere die README jetzt und erstelle einen Draft PR: https://github.com/acme/repo' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));

    await screen.findByTestId('github-action-preview');
    expect(runtime.agentStart).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Repository-Ausführung starten' }));

    await waitFor(() => expect(runtime.agentStart).toHaveBeenCalledOnce());
    expect(runtime.agentStart).toHaveBeenCalledWith(expect.objectContaining({
      repoUrl: 'https://github.com/acme/repo',
      branch: 'main',
      mission: 'README aktualisieren',
    }));
    expect(runtime.prepareDraftPr).not.toHaveBeenCalled();
    expect(runtime.createDraftPr).not.toHaveBeenCalled();
    await screen.findByRole('button', { name: 'Draft PR erstellen' });
    fireEvent.click(screen.getByRole('button', { name: 'Draft PR erstellen' }));
    await waitFor(() => expect(runtime.prepareDraftPr).toHaveBeenCalledWith('job-release-1'));
    await waitFor(() => expect(runtime.createDraftPr).toHaveBeenCalledWith('job-release-1'));
    expect(await screen.findByText(/github\.com\/acme\/repo\/pull\/42/)).toBeDefined();
    expect(runtime.reply).not.toHaveBeenCalled();
  });

  it('keeps a direct patch in the runtime workspace until Draft-PR publication is explicitly requested', async () => {
    runtime.parseRepo.mockReturnValue({
      owner: 'acme', repo: 'repo', branch: 'main', path: '', name: 'repo', repoUrl: 'https://github.com/acme/repo',
    });
    runtime.interpret.mockResolvedValue({
      ok: true,
      interpretation: {
        mode: 'action', intent: 'direct_patch', actionDisposition: 'execute', assistantText: '',
        actionTitle: 'README aktualisieren', confidence: 0.97, language: 'de', model: 'free-route-1', fallbackUsed: false,
      },
    });
    runtime.agentStart.mockResolvedValue({
      jobId: 'job-release-2', workspaceId: 'ws-release-2', runtimeId: 'run-release-2', status: 'completed',
      repoUrl: 'https://github.com/acme/repo', branch: 'main', changedFiles: ['README.md'], events: [],
    });

    render(<PlayReleaseChat />);
    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'Ändere die README jetzt: https://github.com/acme/repo' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));

    await screen.findByTestId('github-action-preview');
    expect(runtime.agentStart).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Repository-Ausführung starten' }));
    await waitFor(() => expect(runtime.agentStart).toHaveBeenCalledOnce());
    expect(await screen.findByText(/Kein externer GitHub-Write wurde ausgeführt/)).toBeDefined();
    expect(runtime.prepareDraftPr).not.toHaveBeenCalled();
    expect(runtime.createDraftPr).not.toHaveBeenCalled();
  });

  it('recovers a user-owned repository action when the online model returns malformed prose', async () => {
    const target = {
      owner: 'acme', repo: 'repo', branch: 'main', path: '', name: 'repo', repoUrl: 'https://github.com/acme/repo',
    };
    runtime.parseRepo.mockReturnValueOnce(target).mockReturnValue(null);
    runtime.interpret
      .mockResolvedValueOnce({
        ok: true,
        interpretation: {
          mode: 'action', intent: 'load_repo', actionDisposition: 'execute', assistantText: '',
          actionTitle: 'Repository laden', confidence: 0.99, language: 'de', model: 'free-route-1', fallbackUsed: false,
        },
      })
      .mockResolvedValueOnce({
        ok: false,
        error: 'invalid action contract',
        rawContent: 'Ungebundene Modellprosa darf keine Repository-Aktion steuern.',
      });

    render(<PlayReleaseChat />);
    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'https://github.com/acme/repo' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));
    expect(await screen.findByText(/Repository-Ziel gebunden: acme\/repo/)).toBeDefined();

    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'Bitte passe die repository doku an mit dem heutigen Datum!' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));

    await screen.findByRole('button', { name: 'Repository-Ausführung starten' });
    expect(screen.getByText(/Auftrag: Bitte passe die repository doku an mit dem heutigen Datum!/)).toBeDefined();
    expect(screen.queryByText(/Ungebundene Modellprosa/)).toBeNull();
    expect(runtime.agentStart).not.toHaveBeenCalled();
    expect(runtime.reply).not.toHaveBeenCalled();
  });

  it('keeps an explicitly entered PAT outside chat and passes it only to repository execution', async () => {
    const sessionToken = 'github_pat_' + 'a'.repeat(24);
    runtime.parseRepo.mockReturnValue({
      owner: 'acme', repo: 'repo', branch: 'main', path: '', name: 'repo', repoUrl: 'https://github.com/acme/repo',
    });
    runtime.interpret.mockResolvedValue({
      ok: true,
      interpretation: {
        mode: 'action', intent: 'direct_patch', actionDisposition: 'execute', assistantText: '',
        actionTitle: 'README aktualisieren', confidence: 0.97, language: 'de', model: 'free-route-1', fallbackUsed: false,
      },
    });
    runtime.agentStart.mockResolvedValue({
      jobId: 'job-pat-1', workspaceId: 'ws-pat-1', runtimeId: 'run-pat-1', status: 'completed',
      repoUrl: 'https://github.com/acme/repo', branch: 'main', changedFiles: ['README.md'], events: [],
    });

    render(<PlayReleaseChat />);
    fireEvent.click(screen.getByRole('button', { name: /GitHub/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Zugang eingeben' }));
    fireEvent.change(screen.getByLabelText(/GitHub Token/), { target: { value: sessionToken } });
    fireEvent.click(screen.getByRole('button', { name: 'Übernehmen' }));

    expect(screen.queryByText(sessionToken)).toBeNull();
    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'Ändere die README: https://github.com/acme/repo' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));
    await screen.findByRole('button', { name: 'Repository-Ausführung starten' });
    fireEvent.click(screen.getByRole('button', { name: 'Repository-Ausführung starten' }));

    await waitFor(() => expect(runtime.agentStart).toHaveBeenCalledWith(expect.objectContaining({
      githubAccessToken: sessionToken,
      repoUrl: 'https://github.com/acme/repo',
    })));
    expect(runtime.reply).not.toHaveBeenCalled();
  });

  it('sends chat through the current Sovereign LLM bridge and renders the real reply', async () => {
    render(<PlayReleaseChat />);
    const input = screen.getByLabelText('Nachricht an Sovereign');

    fireEvent.change(input, { target: { value: 'Hallo Sovereign' } });
    fireEvent.click(screen.getByLabelText('Senden'));

    await waitFor(() => expect(runtime.reply).toHaveBeenCalledOnce());
    const [request] = runtime.reply.mock.calls[0];
    expect(request.model).toBe('sovereign-fast');
    expect(request.messages.at(-1)).toEqual({ role: 'user', content: 'Hallo Sovereign' });
    expect(await screen.findByText('Antwort aus der aktuellen Sovereign LLM-Runtime.')).toBeDefined();
  });

  it('pins an explicitly selected free route instead of silently changing the requested route', async () => {
    render(<PlayReleaseChat />);
    const routeSelect = screen.getByLabelText('LLM Route');
    await screen.findByRole('option', { name: 'FREE · Free Revolver' });
    fireEvent.change(routeSelect, { target: { value: 'free-route-1' } });

    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), { target: { value: 'Nutze diese Route' } });
    fireEvent.click(screen.getByLabelText('Senden'));

    await waitFor(() => expect(runtime.reply).toHaveBeenCalledOnce());
    expect(runtime.reply.mock.calls[0][0].model).toBe('free-route-1');
    expect(screen.getByText(/Route fixiert: FREE · Free Revolver/)).toBeDefined();
  });

  it('blocks secret-shaped input before any LLM request', async () => {
    runtime.evaluateInputPolicy.mockReturnValueOnce({ shouldBlock: true });
    render(<PlayReleaseChat />);

    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), { target: { value: 'ghp_secret_value_for_test' } });
    fireEvent.click(screen.getByLabelText('Senden'));

    await waitFor(() => expect(screen.getByText(/wurde nicht an das LLM gesendet/i)).toBeDefined());
    expect(runtime.reply).not.toHaveBeenCalled();
    expect(screen.queryByText('ghp_secret_value_for_test')).toBeNull();
  });

  it('shows the backend blocker honestly and rechecks without blind resend', async () => {
    runtime.reply.mockResolvedValueOnce({
      ok: false,
      error: 'free_route_revolver_exhausted',
      route: '/api/llm/chat',
      diagnostic: {
        nextAction: 'Auf den Kontingent-Reset warten oder eine Free-Route prüfen.',
      },
    });
    render(<PlayReleaseChat />);

    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), { target: { value: 'Bitte antworte' } });
    fireEvent.click(screen.getByLabelText('Senden'));

    expect(await screen.findByText(/LLM-Anfrage blockiert:/)).toBeDefined();
    await waitFor(() => expect(runtime.catalog).toHaveBeenCalled());
    await waitFor(() => expect(runtime.health).toHaveBeenCalled());
    const catalogCallsBeforeRecheck = runtime.catalog.mock.calls.length;
    const healthCallsBeforeRecheck = runtime.health.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Runtime und Routen neu prüfen' }));

    await waitFor(() => expect(runtime.catalog.mock.calls.length).toBeGreaterThan(catalogCallsBeforeRecheck));
    await waitFor(() => expect(runtime.health.mock.calls.length).toBeGreaterThan(healthCallsBeforeRecheck));
    expect(runtime.catalog).toHaveBeenCalledWith(undefined, 'execution');
    expect(runtime.reply).toHaveBeenCalledOnce();
    expect(await screen.findByText(/Die ursprüngliche Anfrage wurde nicht erneut gesendet/)).toBeDefined();
    expect(screen.getByLabelText('Nachricht an Sovereign')).toHaveValue('Bitte antworte');
  });

  it('preserves an authentication blocker when generic route health is green', async () => {
    runtime.reply.mockResolvedValueOnce({
      ok: false,
      error: 'Nicht eingeloggt',
      route: '/api/llm/chat',
      diagnostic: {
        status: 401,
        scope: 'authentication',
        nextAction: 'Backend-Session erneut bestätigen oder anmelden.',
      },
    });
    render(<PlayReleaseChat />);

    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), { target: { value: 'Bitte sichere Antwort' } });
    fireEvent.click(screen.getByLabelText('Senden'));

    expect(await screen.findByText(/LLM-Anfrage blockiert:/)).toBeDefined();
    await waitFor(() => expect(runtime.catalog).toHaveBeenCalled());
    await waitFor(() => expect(runtime.health).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'Runtime und Routen neu prüfen' }));

    expect(await screen.findByText(/Routenprüfung ersetzt diese Freigabe nicht/)).toBeDefined();
    expect(runtime.catalog).not.toHaveBeenCalledWith(undefined, 'execution');
    expect(runtime.health).not.toHaveBeenCalledWith();
    expect(runtime.reply).toHaveBeenCalledOnce();
    expect(screen.getByLabelText('Nachricht an Sovereign')).toHaveValue('');
  });
});
