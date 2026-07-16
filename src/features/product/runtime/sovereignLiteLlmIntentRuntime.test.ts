import { afterEach, describe, expect, it, vi } from 'vitest';
import { SOVEREIGN_WORKER_CHAT } from './devChatWorkerBridge';
import {
  fetchSovereignLiteLlmInterpretation,
  SOVEREIGN_INTENT_TIMEOUT_MS,
  SOVEREIGN_LITELLM_CHAT,
  SOVEREIGN_LITELLM_ROUTES,
} from './sovereignLiteLlmIntentRuntime';

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('sovereignLiteLlmIntentRuntime', () => {
  it('resolves an enabled backend route and interprets language through LiteLLM', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [
          { id: 'sovereign-chat', defaultModelId: 'openai/gpt-5.2-mini', enabled: true },
        ],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'openai/gpt-5.2-mini',
        choices: [{ message: { content: JSON.stringify({
          mode: 'action',
          intent: 'draft_pr',
          assistant_text: 'Ich habe den Auftrag verstanden. Die Runtime prüft jetzt die Gates.',
          action_title: 'Routing reparieren und Draft PR erstellen',
          confidence: 0.96,
          language: 'de',
        }) } }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      preferredModel: 'deepseek-r1',
      text: 'Repariere den Routingfehler und mach am Ende einen Draft PR.',
      requestId: '00000000-0000-4000-8000-000000000101',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      mode: 'action',
      intent: 'draft_pr',
      model: 'openai/gpt-5.2-mini',
      fallbackUsed: true,
    });
    expect(fetchMock).toHaveBeenNthCalledWith(1, SOVEREIGN_LITELLM_ROUTES, expect.objectContaining({
      method: 'GET',
      credentials: 'include',
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, SOVEREIGN_LITELLM_CHAT, expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request.model).toBe('openai/gpt-5.2-mini');
    expect(request.requestId).toBe('00000000-0000-4000-8000-000000000101');
    expect(request.stream).toBe(false);
  });

  it('uses the requested model when the enabled route catalog contains it', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [
          { id: 'fast', defaultModelId: 'mistral-7b', enabled: true },
          { id: 'power', defaultModelId: 'deepseek-r1', enabled: true },
        ],
      }))
      .mockResolvedValueOnce(jsonResponse({
        choices: [{ message: { content: JSON.stringify({
          mode: 'chat',
          intent: 'free_chat',
          assistant_text: 'Das LLM versteht die Sprache; die Runtime kontrolliert nur Aktionen.',
          action_title: '',
          confidence: 0.98,
          language: 'de',
        }) } }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      preferredModel: 'deepseek-r1',
      text: 'Warum trennen wir Sprache und Runtime?',
      requestId: '00000000-0000-4000-8000-000000000102',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation?.model).toBe('deepseek-r1');
    expect(result.interpretation?.fallbackUsed).toBe(false);
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request.model).toBe('deepseek-r1');
  });

  it('rejects malformed provider text as action evidence', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [{ id: 'sovereign-chat', defaultModelId: 'model-a', enabled: true }],
      }))
      .mockResolvedValueOnce(jsonResponse({
        choices: [{ message: { content: 'Ich habe alles geändert und der PR ist fertig.' } }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Mach den Fix.',
      requestId: '00000000-0000-4000-8000-000000000103',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
    expect(result.rawContent).toContain('PR ist fertig');
    expect(result.diagnostic?.nextAction).toContain('Offline-Fallback');
  });

  it('does not fall back to the legacy Cloudflare worker when no LiteLLM route is enabled', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({
      routes: [{ id: 'disabled', defaultModelId: 'old-model', enabled: false }],
    }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Erkläre den aktuellen Zustand.',
      requestId: '00000000-0000-4000-8000-000000000104',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('Keine aktivierte LiteLLM-Route');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === SOVEREIGN_WORKER_CHAT)).toBe(false);
  });

  it('reports the backend credit gate without attempting a second route', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [{ id: 'sovereign-chat', defaultModelId: 'model-a', enabled: true }],
      }))
      .mockResolvedValueOnce(jsonResponse({ error: 'insufficient_credits' }, 402));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Hallo',
      requestId: '00000000-0000-4000-8000-000000000105',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.diagnostic).toMatchObject({
      route: SOVEREIGN_LITELLM_CHAT,
      status: 402,
      canClientFix: false,
    });
    expect(result.diagnostic?.nextAction).toContain('keine zweite Frontend-Abbuchung');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('keeps the interpretation timeout bounded', () => {
    expect(SOVEREIGN_INTENT_TIMEOUT_MS).toBe(30_000);
  });
});
