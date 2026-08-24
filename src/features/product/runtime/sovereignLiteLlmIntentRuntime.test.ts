import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEV_CHAT_WORKER_DEFAULT_MODEL, SOVEREIGN_WORKER_CHAT } from './devChatWorkerBridge';
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

function freeRoute(id: string, defaultModelId: string, enabled = true) {
  return {
    id,
    defaultModelId,
    enabled,
    provider: 'freellm',
    billingCategory: 'free',
    fundingMode: 'provider_free_quota',
  };
}

function paidRoute(id: string, defaultModelId: string, category: 'standard' | 'premium' = 'standard') {
  return {
    id,
    defaultModelId,
    enabled: true,
    provider: 'openrouter',
    billingCategory: category,
    fundingMode: 'provider_priced',
  };
}

describe('sovereignLiteLlmIntentRuntime', () => {
  it('binds a receiver-sensitive global fetch for German action intent classification', async () => {
    const calls: string[] = [];
    vi.stubGlobal('fetch', async function receiverSensitiveFetch(
      this: typeof globalThis,
      url: RequestInfo | URL,
      _init?: RequestInit,
    ): Promise<Response> {
      if (this !== globalThis) throw new TypeError('Illegal invocation');
      calls.push(String(url));
      if (calls.length === 1) {
        return jsonResponse({
          routes: [freeRoute('sovereign-chat', 'openai/gpt-5.2-mini')],
        });
      }
      return jsonResponse({
        model: 'openai/gpt-5.2-mini',
        choices: [{ message: { content: JSON.stringify({
          mode: 'action',
          intent: 'draft_pr',
          action_disposition: 'execute',
          assistant_text: 'Ich habe den Auftrag verstanden. Die Runtime prüft jetzt die Gates.',
          action_title: 'Routing reparieren und Draft PR erstellen',
          confidence: 0.97,
          language: 'de',
        }) } }],
      });
    });

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Repariere den Routingfehler und mach am Ende einen Draft PR.',
      requestId: '00000000-0000-4000-8000-000000000109',
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      mode: 'action',
      intent: 'draft_pr',
      actionDisposition: 'execute',
      language: 'de',
    });
    expect(calls).toEqual([SOVEREIGN_LITELLM_ROUTES, SOVEREIGN_LITELLM_CHAT]);
  });

  it('resolves the abstract PAL alias through the current backend catalog without calling it a fallback', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('sovereign-chat', 'openai/gpt-5.2-mini')],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'openai/gpt-5.2-mini',
        choices: [{ message: { content: JSON.stringify({
          mode: 'chat',
          intent: 'free_chat',
          action_disposition: 'review',
          assistant_text: 'Auto-Routing nutzt die aktuelle Backend-Route.',
          action_title: '',
          confidence: 0.99,
          language: 'de',
        }) } }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      preferredModel: DEV_CHAT_WORKER_DEFAULT_MODEL,
      text: 'Welche Route nutzt Auto?',
      requestId: '00000000-0000-4000-8000-000000000111',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation?.fallbackUsed).toBe(false);
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request.model).toBe('sovereign-chat');
  });

  it('fails closed when a preferred route is absent instead of interpreting through another model', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({
      routes: [
        freeRoute('sovereign-chat', 'openai/gpt-5.2-mini'),
      ],
    }));

    const result = await fetchSovereignLiteLlmInterpretation({
      preferredModel: 'deepseek-r1',
      text: 'Repariere den Routingfehler und mach am Ende einen Draft PR.',
      requestId: '00000000-0000-4000-8000-000000000101',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
    expect(result.error).toContain('Keine aktivierte OpenRouter- oder FreeLLM-Route');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenNthCalledWith(1, SOVEREIGN_LITELLM_ROUTES, expect.objectContaining({
      method: 'GET',
      credentials: 'include',
    }));
  });

  it('uses the requested model when the enabled route catalog contains it', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [
          freeRoute('fast', 'mistral-7b'),
          paidRoute('power', 'deepseek-r1'),
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
    expect(request.model).toBe('power');
  });

  it('skips a transport/billing mismatch instead of posting it as the active route', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [
          {
            id: 'misrouted',
            defaultModelId: 'wrong-paid-model',
            enabled: true,
            provider: 'freellm',
            billingCategory: 'standard',
            fundingMode: 'provider_priced',
          },
          freeRoute('verified-free', 'free-model'),
        ],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'free-model',
        choices: [{ message: { content: JSON.stringify({
          mode: 'chat',
          intent: 'free_chat',
          assistant_text: 'Die verifizierte freie Route wurde verwendet.',
          action_title: '',
          confidence: 0.99,
          language: 'de',
        }) } }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Hallo',
      requestId: '00000000-0000-4000-8000-000000000110',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request.model).toBe('verified-free');
  });

  it('preserves the LLM distinction between startup and completion status', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('status', 'model-status')],
      }))
      .mockResolvedValueOnce(jsonResponse({
        choices: [{ message: { content: JSON.stringify({
          mode: 'chat',
          intent: 'status',
          action_disposition: 'review',
          assistant_text: 'Ich prüfe, ob die Ausführung bereits läuft.',
          action_title: '',
          is_startup: true,
          confidence: 0.99,
          language: 'de',
        }) } }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Arbeitet er schon?',
      requestId: '00000000-0000-4000-8000-000000000106',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      intent: 'status',
      isStartup: true,
    });
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request.messages[0].content).toContain('"is_startup":false');
    expect(request.messages[0].content).toContain('begonnen hat oder aktuell läuft');
    expect(request.messages[0].content).toContain('für fertig/abgeschlossen/Fortschritt bleibt is_startup=false');
  });

  it('rejects malformed provider text as action evidence', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('sovereign-chat', 'model-a')],
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

  it('does not fall back to the legacy Cloudflare worker when no direct LLM route is enabled', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({
      routes: [freeRoute('disabled', 'old-model', false)],
    }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Erkläre den aktuellen Zustand.',
      requestId: '00000000-0000-4000-8000-000000000104',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('Keine aktivierte OpenRouter- oder FreeLLM-Route');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === SOVEREIGN_WORKER_CHAT)).toBe(false);
  });

  it('classifies HTTP 401 as a recoverable backend-session blocker', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('sovereign-chat', 'model-a')],
      }))
      .mockResolvedValueOnce(jsonResponse({ error: 'Nicht eingeloggt' }, 401));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Hallo',
      requestId: '00000000-0000-4000-8000-000000000107',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.diagnostic).toMatchObject({
      route: SOVEREIGN_LITELLM_CHAT,
      status: 401,
      scope: 'authentication',
      canClientFix: true,
    });
    expect(result.diagnostic?.nextAction).toMatch(/Session|anmelden/i);
  });

  it('classifies HTTP 403 as authorization denial without proposing login as the fix', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('sovereign-chat', 'model-a')],
      }))
      .mockResolvedValueOnce(jsonResponse({ error: 'Zugriff verweigert' }, 403));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Hallo',
      requestId: '00000000-0000-4000-8000-000000000108',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.diagnostic).toMatchObject({
      route: SOVEREIGN_LITELLM_CHAT,
      status: 403,
      scope: 'authentication',
      canClientFix: false,
    });
    expect(result.diagnostic?.nextAction).toContain('Berechtigung');
    expect(result.diagnostic?.nextAction).toContain('erneutes Anmelden');
  });

  it('reports the backend credit gate without attempting a second route', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('sovereign-chat', 'model-a')],
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
