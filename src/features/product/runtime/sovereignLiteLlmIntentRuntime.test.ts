import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEV_CHAT_WORKER_DEFAULT_MODEL, SOVEREIGN_WORKER_CHAT } from './devChatWorkerBridge';
import {
  fetchSovereignLiteLlmInterpretation,
  SOVEREIGN_CODE_ACTION_ROUTES,
  SOVEREIGN_INTENT_TIMEOUT_MS,
  SOVEREIGN_LITELLM_CHAT,
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
    capabilities: { codeActionContract: true },
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
    capabilities: { codeActionContract: true },
  };
}

function actionEnvelope(overrides: Record<string, unknown> = {}) {
  return {
    mode: 'action',
    intent: 'code_execution',
    action_disposition: 'review',
    clarification_code: 'none',
    is_startup: false,
    confidence: 0.97,
    language: 'de',
    ...overrides,
  };
}

describe('sovereignLiteLlmIntentRuntime structured code-action lane', () => {
  it('binds global fetch, requests only the action-contract catalog, and excludes chat history', async () => {
    const calls: string[] = [];
    const requests: Array<RequestInit | undefined> = [];
    vi.stubGlobal('fetch', async function receiverSensitiveFetch(
      this: typeof globalThis,
      url: RequestInfo | URL,
      init?: RequestInit,
    ): Promise<Response> {
      if (this !== globalThis) throw new TypeError('Illegal invocation');
      calls.push(String(url));
      requests.push(init);
      if (calls.length === 1) {
        return jsonResponse({
          routes: [freeRoute('sovereign-action', 'openai/gpt-5.2-mini')],
        });
      }
      return jsonResponse({
        model: 'openai/gpt-5.2-mini',
        choices: [{
          message: {
            content: JSON.stringify(actionEnvelope({ intent: 'draft_pr' })),
          },
        }],
      });
    });

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Repariere den Routingfehler und mach am Ende einen Draft PR.',
      recentMessages: [{
        role: 'assistant',
        content: 'ghp_secret_from_previous_chat_must_not_be_forwarded',
      }],
      requestId: '00000000-0000-4000-8000-000000000109',
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      mode: 'action',
      intent: 'draft_pr',
      actionDisposition: 'review',
      actionTitle: 'Draft PR vorbereiten',
      assistantText: '',
      language: 'de',
    });
    expect(calls).toEqual([SOVEREIGN_CODE_ACTION_ROUTES, SOVEREIGN_LITELLM_CHAT]);

    const body = JSON.parse(String(requests[1]?.body)) as {
      outputContractId: string;
      routeSelectionMode: string;
      model: string;
      messages: Array<{ role: string; content: string }>;
    };
    expect(body).toMatchObject({
      outputContractId: 'sovereign-code-action-v1',
      routeSelectionMode: 'auto',
      model: 'sovereign-action',
    });
    expect(body.messages).toHaveLength(2);
    expect(body.messages[1]).toEqual({
      role: 'user',
      content: 'Repariere den Routingfehler und mach am Ende einen Draft PR.',
    });
    expect(JSON.stringify(body)).not.toContain('ghp_secret_from_previous_chat');
  });

  it('resolves the abstract PAL alias only through a verified free structured route', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [
          paidRoute('paid-action', 'provider/paid-action'),
          freeRoute('free-action', 'provider/free-action'),
        ],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'provider/free-action',
        choices: [{
          message: {
            content: JSON.stringify(actionEnvelope({ intent: 'direct_patch' })),
          },
        }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      preferredModel: DEV_CHAT_WORKER_DEFAULT_MODEL,
      text: 'Korrigiere den Tippfehler in README.md.',
      requestId: '00000000-0000-4000-8000-000000000111',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      intent: 'direct_patch',
      actionDisposition: 'review',
      fallbackUsed: false,
    });
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request).toMatchObject({
      model: 'free-action',
      routeSelectionMode: 'auto',
    });
  });

  it('fails closed when a preferred route is absent instead of interpreting through another model', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({
      routes: [freeRoute('sovereign-action', 'openai/gpt-5.2-mini')],
    }));

    const result = await fetchSovereignLiteLlmInterpretation({
      preferredModel: 'deepseek-r1',
      text: 'Repariere den Routingfehler und mach am Ende einen Draft PR.',
      requestId: '00000000-0000-4000-8000-000000000101',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
    expect(result.error).toContain('strukturierten Codeauftragsvertrag');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenNthCalledWith(1, SOVEREIGN_CODE_ACTION_ROUTES, expect.objectContaining({
      method: 'GET',
      credentials: 'include',
    }));
  });

  it('honors an explicitly pinned capable paid route without a silent switch', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [
          freeRoute('fast', 'mistral-7b'),
          paidRoute('power', 'deepseek-r1'),
        ],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'deepseek-r1',
        choices: [{
          message: {
            content: JSON.stringify(actionEnvelope({ intent: 'repair_workflow' })),
          },
        }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      preferredModel: 'deepseek-r1',
      text: 'Repariere den fehlgeschlagenen Workflow.',
      requestId: '00000000-0000-4000-8000-000000000102',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      intent: 'repair_workflow',
      model: 'deepseek-r1',
      fallbackUsed: false,
      actionDisposition: 'review',
    });
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request).toMatchObject({
      model: 'power',
      routeSelectionMode: 'pinned',
    });
  });

  it('skips a transport/billing mismatch even when it claims structured capability', async () => {
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
            capabilities: { codeActionContract: true },
          },
          freeRoute('verified-free', 'free-model'),
        ],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'free-model',
        choices: [{ message: { content: JSON.stringify(actionEnvelope()) } }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Behebe den Build.',
      requestId: '00000000-0000-4000-8000-000000000110',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    const request = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(request.model).toBe('verified-free');
  });

  it('renders only the local question selected by a schema-valid clarification_code', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('clarifier', 'model-clarifier')],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'model-clarifier',
        choices: [{
          message: {
            content: JSON.stringify({
              mode: 'clarify',
              intent: 'unknown',
              action_disposition: 'review',
              clarification_code: 'repo_required',
              is_startup: false,
              confidence: 0.99,
              language: 'de',
            }),
          },
        }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Repariere das.',
      requestId: '00000000-0000-4000-8000-000000000106',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      mode: 'chat',
      intent: 'unknown',
      actionDisposition: 'review',
      assistantText: 'Welches Repository soll ich ändern?',
      actionTitle: '',
    });
  });

  it('fails closed when the wire payload includes legacy prose fields', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('clarifier', 'model-clarifier')],
      }))
      .mockResolvedValueOnce(jsonResponse({
        model: 'model-clarifier',
        choices: [{
          message: {
            content: JSON.stringify({
              mode: 'clarify',
              intent: 'unknown',
              action_disposition: 'review',
              clarification_code: 'repo_required',
              is_startup: false,
              confidence: 0.99,
              language: 'de',
              assistant_text: 'Provider-Prosa und Smalltalk dürfen nicht erscheinen.',
              action_title: 'Provider-Titel darf niemals Aktions-Evidence werden.',
            }),
          },
        }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Repariere das.',
      requestId: '00000000-0000-4000-8000-000000000113',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
    expect(result.rawContent).toBeUndefined();
    expect(result.diagnostic?.bodySnippet).toBeUndefined();
  });

  it('rejects model-issued execute authority', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('sovereign-action', 'model-a')],
      }))
      .mockResolvedValueOnce(jsonResponse({
        choices: [{
          message: {
            content: JSON.stringify(actionEnvelope({ action_disposition: 'execute' })),
          },
        }],
      }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Mach den Fix.',
      requestId: '00000000-0000-4000-8000-000000000112',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
  });

  it('discards malformed provider prose without exposing raw content or invoking offline interpretation', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('sovereign-action', 'model-a')],
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
    expect(result.rawContent).toBeUndefined();
    expect(result.diagnostic?.bodySnippet).toBeUndefined();
    expect(result.diagnostic?.nextAction).not.toContain('Offline-Fallback');
    expect(result.diagnostic?.nextAction).toContain('verwerfen');
  });

  it('does not fall back to the legacy worker when no capable direct route exists', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({
      routes: [
        freeRoute('disabled', 'old-model', false),
        {
          ...freeRoute('general-chat', 'chat-model'),
          capabilities: { codeActionContract: false },
        },
      ],
    }));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Repariere den Build.',
      requestId: '00000000-0000-4000-8000-000000000104',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('strukturierten Codeauftragsvertrag');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === SOVEREIGN_WORKER_CHAT)).toBe(false);
  });

  it('classifies HTTP 401 as a recoverable backend-session blocker', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        routes: [freeRoute('sovereign-action', 'model-a')],
      }))
      .mockResolvedValueOnce(jsonResponse({ error: 'Nicht eingeloggt' }, 401));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Repariere den Build.',
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
        routes: [freeRoute('sovereign-action', 'model-a')],
      }))
      .mockResolvedValueOnce(jsonResponse({ error: 'Zugriff verweigert' }, 403));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Repariere den Build.',
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
        routes: [freeRoute('sovereign-action', 'model-a')],
      }))
      .mockResolvedValueOnce(jsonResponse({ error: 'insufficient_credits' }, 402));

    const result = await fetchSovereignLiteLlmInterpretation({
      text: 'Repariere den Build.',
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
