import { describe, expect, it, vi } from 'vitest';
import { fetchSovereignDirectLlmInterpretation } from './sovereignDirectLlmIntentRuntime';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const structuredFreeRoute = {
  id: 'structured-free-route',
  defaultModelId: 'provider/structured-free',
  enabled: true,
  provider: 'freellm',
  billingCategory: 'free',
  fundingMode: 'provider_free_quota',
  capabilities: { codeActionContract: true },
};

function actionEnvelope(overrides: Record<string, unknown> = {}) {
  return {
    mode: 'action',
    intent: 'code_execution',
    action_disposition: 'review',
    clarification_code: 'none',
    is_startup: false,
    confidence: 0.99,
    language: 'de',
    ...overrides,
  };
}

describe('sovereignDirectLlmIntentRuntime code-action binding', () => {
  it.each([
    ['llm_output_contract_violation', 502, 'worker_runtime'],
    ['llm_output_contract_route_unavailable', 409, 'worker_config'],
    ['freellm_upstream_unavailable', 502, 'upstream_provider'],
  ])('classifies %s from the structured blocker rather than HTTP alone', async (blocker, status, scope) => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ routes: [structuredFreeRoute] }))
      .mockResolvedValueOnce(jsonResponse({ blocker }, Number(status))) as unknown as typeof fetch;
    const result = await fetchSovereignDirectLlmInterpretation({
      text: 'Prüfe die Tests.',
      fetchImpl,
      requestId: '88888888-8888-4888-8888-888888888888',
    });
    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
    expect(result.diagnostic?.scope).toBe(scope);
    expect(result.diagnostic?.status).toBe(status);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    if (blocker === 'llm_output_contract_violation') {
      expect(result.diagnostic?.nextAction).toContain('Provider hat geantwortet');
      expect(result.diagnostic?.nextAction).not.toContain('Rate-Limit');
    }
  });

  it('fails closed when a manually pinned route is absent from the action-contract catalog', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ routes: [structuredFreeRoute] })) as unknown as typeof fetch;

    const result = await fetchSovereignDirectLlmInterpretation({
      preferredModel: 'manually-pinned-route-that-disappeared',
      text: 'Prüfe den aktuellen Stand.',
      fetchImpl,
      requestId: '11111111-1111-4111-8111-111111111111',
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('strukturierten Codeauftragsvertrag');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining('?purpose=action-contract'),
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('rejects a general-chat route without verified structured capability', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      routes: [{ ...structuredFreeRoute, capabilities: { codeActionContract: false } }],
    })) as unknown as typeof fetch;

    const result = await fetchSovereignDirectLlmInterpretation({
      text: 'Behebe den Build.',
      fetchImpl,
      requestId: '22222222-2222-4222-8222-222222222222',
    });

    expect(result.ok).toBe(false);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('sends the fixed server-owned review contract and excludes previous chat secrets', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ routes: [structuredFreeRoute] }))
      .mockResolvedValueOnce(jsonResponse({
        model: structuredFreeRoute.defaultModelId,
        choices: [{ message: { content: JSON.stringify(actionEnvelope()) } }],
      })) as unknown as typeof fetch;

    const result = await fetchSovereignDirectLlmInterpretation({
      text: 'Behebe den Build.',
      recentMessages: [{ role: 'user', content: 'ghp_previous_chat_secret_must_not_leave_browser' }],
      fetchImpl,
      requestId: '33333333-3333-4333-8333-333333333333',
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      mode: 'action',
      intent: 'code_execution',
      actionDisposition: 'review',
      actionTitle: 'Repository-Auftrag ausführen',
      assistantText: '',
    });

    const [, request] = vi.mocked(fetchImpl).mock.calls[1];
    const body = JSON.parse(String(request?.body)) as {
      outputContractId: string;
      routeSelectionMode: string;
      model: string;
      messages: Array<{ role: string; content: string }>;
    };
    expect(body).toMatchObject({
      outputContractId: 'sovereign-code-action-v1',
      routeSelectionMode: 'auto',
      model: structuredFreeRoute.id,
    });
    expect(body.messages).toHaveLength(2);
    expect(body.messages[1]).toEqual({ role: 'user', content: 'Behebe den Build.' });
    expect(JSON.stringify(body)).not.toContain('ghp_previous_chat_secret');
  });

  it('rejects any model attempt to grant execution authority', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ routes: [structuredFreeRoute] }))
      .mockResolvedValueOnce(jsonResponse({
        model: structuredFreeRoute.defaultModelId,
        choices: [{
          message: {
            content: JSON.stringify(actionEnvelope({ action_disposition: 'execute' })),
          },
        }],
      })) as unknown as typeof fetch;

    const result = await fetchSovereignDirectLlmInterpretation({
      text: 'Behebe den Build.',
      fetchImpl,
      requestId: '44444444-4444-4444-8444-444444444444',
    });

    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
    expect(result.error).toContain('Codeauftragsvertrag');
  });

  it('maps a schema-valid clarification_code to one fixed local question', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ routes: [structuredFreeRoute] }))
      .mockResolvedValueOnce(jsonResponse({
        model: structuredFreeRoute.defaultModelId,
        choices: [{
          message: {
            content: JSON.stringify({
              mode: 'clarify',
              intent: 'unknown',
              action_disposition: 'review',
              clarification_code: 'expected_result_required',
              is_startup: false,
              confidence: 0.91,
              language: 'de',
            }),
          },
        }],
      })) as unknown as typeof fetch;

    const result = await fetchSovereignDirectLlmInterpretation({
      text: 'Repariere das.',
      fetchImpl,
      requestId: '55555555-5555-4555-8555-555555555555',
    });

    expect(result.ok).toBe(true);
    expect(result.interpretation).toMatchObject({
      mode: 'chat',
      intent: 'unknown',
      actionDisposition: 'review',
      assistantText: 'Welches überprüfbare Ergebnis soll nach der Änderung gelten?',
      actionTitle: '',
    });
  });

  it('rejects legacy provider prose fields instead of displaying or interpreting them', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ routes: [structuredFreeRoute] }))
      .mockResolvedValueOnce(jsonResponse({
        model: structuredFreeRoute.defaultModelId,
        choices: [{
          message: {
            content: JSON.stringify({
              mode: 'clarify',
              intent: 'unknown',
              action_disposition: 'review',
              clarification_code: 'repo_required',
              is_startup: false,
              confidence: 0.91,
              language: 'de',
              assistant_text: 'Provider-Smalltalk darf niemals angezeigt werden.',
              action_title: 'Provider-Titel darf niemals Aktions-Evidence werden.',
            }),
          },
        }],
      })) as unknown as typeof fetch;

    const result = await fetchSovereignDirectLlmInterpretation({
      text: 'Repariere das.',
      fetchImpl,
      requestId: '77777777-7777-4777-8777-777777777777',
    });

    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
    expect(result.rawContent).toBeUndefined();
    expect(result.diagnostic?.bodySnippet).toBeUndefined();
  });

  it('discards invalid provider prose without returning it as chat content or offline evidence', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ routes: [structuredFreeRoute] }))
      .mockResolvedValueOnce(jsonResponse({
        model: structuredFreeRoute.defaultModelId,
        choices: [{ message: { content: 'Ich kann das leider nicht ausführen.' } }],
      })) as unknown as typeof fetch;

    const result = await fetchSovereignDirectLlmInterpretation({
      text: 'Behebe den Build.',
      fetchImpl,
      requestId: '66666666-6666-4666-8666-666666666666',
    });

    expect(result.ok).toBe(false);
    expect(result.interpretation).toBeUndefined();
    expect(result.rawContent).toBeUndefined();
    expect(result.diagnostic?.bodySnippet).toBeUndefined();
    expect(result.diagnostic?.nextAction).not.toContain('Fallback');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});
