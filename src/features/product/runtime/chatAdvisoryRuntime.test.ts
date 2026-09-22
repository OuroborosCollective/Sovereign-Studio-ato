import { describe, expect, it, vi } from 'vitest';
import { fetchSovereignAdvisoryChatReply } from './chatAdvisoryRuntime';

vi.mock('./devChatWorkerBridge', () => ({
  DEV_CHAT_WORKER_DEFAULT_MODEL: 'sovereign-fast',
  fetchDevChatWorkerReply: vi.fn(async (request: {
    model: string;
    messages: readonly { role: string; content: string }[];
  }) => ({
    ok: true,
    content: 'Beratende Antwort ohne Ausführung.',
    actualModel: request.model,
    preferredModel: request.model,
    fallbackUsed: false,
  })),
}));

describe('chatAdvisoryRuntime', () => {
  it('keeps the model path advisory-only and supplies runtime readback as data', async () => {
    const result = await fetchSovereignAdvisoryChatReply({
      text: 'Was ist der aktuelle Job-Status?',
      history: [{ role: 'user', content: 'Hallo' }],
      runtimeContext: {
        jobId: 'agent-123',
        phase: 'EXECUTING',
        sourceStatus: 'running',
        recentReadback: ['observed event'],
      },
    });

    expect(result.ok).toBe(true);
    expect(result.content).toContain('Beratende Antwort');
  });

  it('rejects empty chat messages without invoking any execution capability', async () => {
    await expect(fetchSovereignAdvisoryChatReply({ text: '   ' })).resolves.toMatchObject({
      ok: false,
      error: 'Chat message is empty.',
    });
  });
});
