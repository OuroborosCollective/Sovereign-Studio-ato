import { describe, expect, it, vi } from 'vitest';

const bridge = vi.hoisted(() => ({
  fetchDevChatWorkerReply: vi.fn(),
}));

vi.mock('./devChatWorkerBridge', () => ({
  DEV_CHAT_WORKER_DEFAULT_MODEL: 'sovereign-fast',
  fetchDevChatWorkerReply: bridge.fetchDevChatWorkerReply,
}));

import { fetchSovereignAdvisoryChatReply } from './chatAdvisoryRuntime';

describe('Sovereign advisory chat boundary', () => {
  it('uses the LLM only for conversation and never sends an action schema', async () => {
    bridge.fetchDevChatWorkerReply.mockResolvedValueOnce({
      ok: true,
      content: 'Ja. Dafür brauche ich zuerst noch den Repository-Link.',
      actualModel: 'provider/model',
      fallbackUsed: false,
    });

    const result = await fetchSovereignAdvisoryChatReply({
      text: 'Kannst du prüfen, ob mein Architekturansatz korrekt ist?',
      recentMessages: [
        { role: 'user', content: 'Ich möchte die Runtime umbauen.' },
        { role: 'assistant', content: 'Erzähl mir zuerst, welchen Pfad du ändern willst.' },
      ],
      runtimeContext: 'active_run=none',
    });

    expect(result).toEqual({
      ok: true,
      content: 'Ja. Dafür brauche ich zuerst noch den Repository-Link.',
      model: 'provider/model',
      fallbackUsed: false,
    });

    const request = bridge.fetchDevChatWorkerReply.mock.calls[0]?.[0];
    expect(request.messages[0].role).toBe('system');
    expect(request.messages[0].content).toContain('Ein Auftrag entsteht ausschließlich');
    expect(request.messages[0].content).not.toContain('action_disposition');
    expect(request.messages.at(-1)).toEqual({
      role: 'user',
      content: 'Kannst du prüfen, ob mein Architekturansatz korrekt ist?',
    });
  });

  it('fails closed when the advisory route is unavailable and never converts the message into an action', async () => {
    bridge.fetchDevChatWorkerReply.mockResolvedValueOnce({
      ok: false,
      error: 'upstream unavailable',
      actualModel: 'sovereign-fast',
      diagnostic: { scope: 'upstream_provider' },
    });

    const result = await fetchSovereignAdvisoryChatReply({
      text: 'Was hältst du von dieser Architektur?',
    });

    expect(result.ok).toBe(false);
    expect(result).not.toHaveProperty('content');
    expect(bridge.fetchDevChatWorkerReply).toHaveBeenCalledTimes(1);
  });
});
