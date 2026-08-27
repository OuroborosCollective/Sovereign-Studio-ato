import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PlayReleaseChat } from './features/release/PlayReleaseChat';

const runtime = vi.hoisted(() => ({
  catalog: vi.fn(),
  health: vi.fn(),
  reply: vi.fn(),
  evaluateInputPolicy: vi.fn(),
  refreshUser: vi.fn(),
  logout: vi.fn(),
}));

vi.mock('./features/product/runtime/devChatWorkerBridge', () => ({
  DEV_CHAT_WORKER_DEFAULT_MODEL: 'sovereign-fast',
  fetchSovereignLlmRouteCatalog: runtime.catalog,
  fetchDevChatWorkerHealth: runtime.health,
  fetchDevChatWorkerReply: runtime.reply,
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
  runtime.evaluateInputPolicy.mockReturnValue({ shouldBlock: false });
  runtime.refreshUser.mockResolvedValue(undefined);
  runtime.logout.mockResolvedValue(undefined);
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
    expect(screen.getByText(/GitHub ist noch nicht als bestätigte User-Verbindung sichtbar/)).toBeDefined();
  });

  it('loads the authenticated current route catalog and keeps the free-first default', async () => {
    render(<PlayReleaseChat />);

    await waitFor(() => expect(runtime.catalog).toHaveBeenCalled());
    expect(screen.getByRole('option', { name: 'Auto · FreeLLM zuerst' })).toBeDefined();
    expect(await screen.findByRole('option', { name: 'FREE · Free Revolver' })).toBeDefined();
    expect(screen.getByText('release@example.test')).toBeDefined();
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

  it('shows the backend blocker honestly and offers a correlated retry', async () => {
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
