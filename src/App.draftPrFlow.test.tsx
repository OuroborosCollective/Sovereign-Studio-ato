import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PlayReleaseChat } from './features/release/PlayReleaseChat';

const runtime = vi.hoisted(() => ({
  catalog: vi.fn(),
  health: vi.fn(),
  reply: vi.fn(),
  repoTree: vi.fn(),
  interpret: vi.fn(),
  evaluateInputPolicy: vi.fn(),
  refreshUser: vi.fn(),
  logout: vi.fn(),
  agentStart: vi.fn(),
  agentGet: vi.fn(),
  agentPrepare: vi.fn(),
  agentCreate: vi.fn(),
}));

vi.mock('./features/product/runtime/devChatWorkerBridge', async () => {
  const actual = await vi.importActual<typeof import('./features/product/runtime/devChatWorkerBridge')>(
    './features/product/runtime/devChatWorkerBridge',
  );
  return {
    ...actual,
    DEV_CHAT_WORKER_DEFAULT_MODEL: 'sovereign-fast',
    fetchSovereignLlmRouteCatalog: runtime.catalog,
    fetchDevChatWorkerHealth: runtime.health,
    fetchDevChatWorkerReply: runtime.reply,
    fetchDevChatRepoTree: runtime.repoTree,
  };
});

vi.mock('./features/product/runtime/sovereignDirectLlmIntentRuntime', () => ({
  fetchSovereignDirectLlmInterpretation: runtime.interpret,
}));

vi.mock('./features/product/runtime/sovereignAgentClient', () => ({
  SovereignAgentClient: class {
    startJob = runtime.agentStart;
    getJob = runtime.agentGet;
    prepareDraftPr = runtime.agentPrepare;
    createDraftPr = runtime.agentCreate;
  },
}));

vi.mock('./features/product/runtime/secureInputGuard', () => ({
  evaluateInputPolicy: runtime.evaluateInputPolicy,
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

const COMPLETE_JOB = {
  jobId: 'job-release-1',
  status: 'completed' as const,
  repoUrl: 'https://github.com/acme/demo',
  branch: 'main',
  changedFiles: ['README.md'],
  events: [
    {
      at: 1_777_777_777_000,
      level: 'success' as const,
      stage: 'tests',
      message: 'Targeted tests passed.',
    },
  ],
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
  runtime.repoTree.mockResolvedValue({
    ok: true,
    snapshot: {
      owner: 'acme',
      repo: 'demo',
      branch: 'main',
      name: 'demo',
      repoUrl: 'https://github.com/acme/demo',
      headSha: '1234567890abcdef1234567890abcdef12345678',
      fileCount: 1,
      files: [],
      filePaths: ['README.md'],
      dirs: [],
    },
  });
  runtime.interpret.mockResolvedValue({
    ok: true,
    interpretation: {
      mode: 'chat',
      intent: 'free_chat',
      actionDisposition: 'review',
      assistantText: 'Repo-Frage beantwortet.',
      actionTitle: '',
      confidence: 0.95,
      language: 'de',
      model: 'free-route-1',
      fallbackUsed: false,
    },
  });
  runtime.agentStart.mockResolvedValue(COMPLETE_JOB);
  runtime.agentGet.mockResolvedValue(COMPLETE_JOB);
  runtime.agentPrepare.mockResolvedValue({
    ok: true,
    jobId: 'job-release-1',
    draftPrPreparation: {
      allowed: true,
      decision: 'ALLOW',
      canCreateDraftPr: true,
      blockers: [],
      headBranch: 'sovereign/release-test',
      baseBranch: 'main',
    },
  });
  runtime.agentCreate.mockResolvedValue({
    ok: true,
    jobId: 'job-release-1',
    draftPrCreate: {
      allowed: true,
      status: 'created',
      prUrl: 'https://github.com/acme/demo/pull/42',
      headSha: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      publishedHeadSha: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      readbackHeadSha: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      prNumber: 42,
      draftVerified: true,
      prStateVerified: 'open',
      headBranch: 'sovereign/release-test',
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
  runtime.evaluateInputPolicy.mockReturnValue({ shouldBlock: false });
  runtime.refreshUser.mockResolvedValue(undefined);
  runtime.logout.mockResolvedValue(undefined);
});

describe('Play release chat + GitHub coding runtime integration', () => {
  it('loads the authenticated route catalog and keeps the free-first default', async () => {
    render(<PlayReleaseChat />);

    await waitFor(() => expect(runtime.catalog).toHaveBeenCalled());
    expect(screen.getByRole('option', { name: 'Auto · FreeLLM zuerst' })).toBeDefined();
    expect(await screen.findByRole('option', { name: 'FREE · Free Revolver' })).toBeDefined();
    expect(screen.getByText('release@example.test')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Repository verbinden' })).toBeDefined();
  });

  it('keeps ordinary chat on the current Sovereign LLM bridge when no repo is active', async () => {
    render(<PlayReleaseChat />);
    const input = screen.getByLabelText('Nachricht an Sovereign');

    fireEvent.change(input, { target: { value: 'Hallo Sovereign' } });
    fireEvent.click(screen.getByLabelText('Senden'));

    await waitFor(() => expect(runtime.reply).toHaveBeenCalledOnce());
    expect(runtime.interpret).not.toHaveBeenCalled();
    const [request] = runtime.reply.mock.calls[0];
    expect(request.model).toBe('sovereign-fast');
    expect(request.messages.at(-1)).toEqual({ role: 'user', content: 'Hallo Sovereign' });
    expect(await screen.findByText('Antwort aus der aktuellen Sovereign LLM-Runtime.')).toBeDefined();
  });

  it('executes a typed coding request against a GitHub repo and returns a verified draft PR', async () => {
    runtime.interpret.mockResolvedValueOnce({
      ok: true,
      interpretation: {
        mode: 'action',
        intent: 'direct_patch',
        actionDisposition: 'execute',
        assistantText: 'Ich führe die Änderung aus.',
        actionTitle: 'README Hinweis ergänzen',
        confidence: 0.99,
        language: 'de',
        model: 'free-route-1',
        fallbackUsed: false,
      },
    });

    render(<PlayReleaseChat />);
    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'Ändere in https://github.com/acme/demo die README und führe es aus.' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));

    await waitFor(() => expect(runtime.interpret).toHaveBeenCalledOnce());
    await waitFor(() => expect(runtime.agentStart).toHaveBeenCalledOnce());
    expect(runtime.agentStart.mock.calls[0][0]).toMatchObject({
      repoUrl: 'https://github.com/acme/demo',
      branch: 'main',
      mission: 'README Hinweis ergänzen',
      provisionWorkspace: true,
      cloneRepo: true,
    });
    expect(runtime.reply).not.toHaveBeenCalled();

    await waitFor(() => expect(runtime.agentPrepare).toHaveBeenCalledWith('job-release-1'));
    await waitFor(() => expect(runtime.agentCreate).toHaveBeenCalledWith('job-release-1'));
    expect(await screen.findByRole('link', { name: 'https://github.com/acme/demo/pull/42' })).toBeDefined();
    expect(screen.getByLabelText('Sovereign Aktivitätsverlauf')).toBeDefined();
    expect(await screen.findByText(/Küken hat fertig gepiepst/)).toBeDefined();
  });

  it('requires explicit execution when the LLM marks the coding action for review', async () => {
    runtime.interpret.mockResolvedValueOnce({
      ok: true,
      interpretation: {
        mode: 'action',
        intent: 'code_execution',
        actionDisposition: 'review',
        assistantText: 'Änderung verstanden.',
        actionTitle: 'Tests reparieren',
        confidence: 0.91,
        language: 'de',
        model: 'free-route-1',
        fallbackUsed: false,
      },
    });

    render(<PlayReleaseChat />);
    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'Prüfe https://github.com/acme/demo und repariere die Tests.' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));

    const execute = await screen.findByRole('button', { name: 'Änderung jetzt ausführen' });
    expect(runtime.agentStart).not.toHaveBeenCalled();

    fireEvent.click(execute);
    await waitFor(() => expect(runtime.agentStart).toHaveBeenCalledOnce());
  });

  it('uses the typed interpretation for repo questions without mutating the repository', async () => {
    render(<PlayReleaseChat />);
    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), {
      target: { value: 'Was macht dieses Repository? https://github.com/acme/demo' },
    });
    fireEvent.click(screen.getByLabelText('Senden'));

    await waitFor(() => expect(runtime.interpret).toHaveBeenCalledOnce());
    expect(runtime.agentStart).not.toHaveBeenCalled();
    expect(await screen.findByText('Repo-Frage beantwortet.')).toBeDefined();
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

  it('blocks secret-shaped input before any LLM or agent request', async () => {
    runtime.evaluateInputPolicy.mockReturnValueOnce({ shouldBlock: true });
    render(<PlayReleaseChat />);

    fireEvent.change(screen.getByLabelText('Nachricht an Sovereign'), { target: { value: 'ghp_secret_value_for_test' } });
    fireEvent.click(screen.getByLabelText('Senden'));

    await waitFor(() => expect(screen.getByText(/wurde nicht an das LLM gesendet/i)).toBeDefined());
    expect(runtime.reply).not.toHaveBeenCalled();
    expect(runtime.interpret).not.toHaveBeenCalled();
    expect(runtime.agentStart).not.toHaveBeenCalled();
    expect(screen.queryByText('ghp_secret_value_for_test')).toBeNull();
  });

  it('shows backend chat blockers honestly and offers a correlated retry', async () => {
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
    expect(screen.getByRole('button', { name: 'Letzte Anfrage erneut versuchen' })).toBeDefined();
  });
});
