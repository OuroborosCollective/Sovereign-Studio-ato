import { describe, expect, it, vi } from 'vitest';
import {
  buildOfflineIntentInterpretation,
  parseOnlineIntentInterpretation,
  resolveSovereignIntent,
} from './sovereignIntentInterpretationRuntime';

describe('Sovereign Intent Interpretation Runtime', () => {
  it('parses a strict online LLM interpretation', () => {
    const interpretation = parseOnlineIntentInterpretation(
      JSON.stringify({
        intent: 'draft_pr',
        complexity: 'complex',
        normalizedRequest: 'Fix the routing defect and create a Draft PR.',
        assistantMessage: 'Ich habe den Reparaturauftrag verstanden. Die Runtime prüft jetzt die Ausführungsgates.',
        requiresWrite: true,
        requiresDraftPr: true,
        confidence: 0.94,
      }),
      {
        text: 'Mach den Fehler fertig und am Ende einen Draft PR.',
        modelId: 'sovereign-intent-model',
        requestId: '00000000-0000-4000-8000-000000000001',
      },
    );

    expect(interpretation.source).toBe('online_llm');
    expect(interpretation.intent).toBe('draft_pr');
    expect(interpretation.assistantMessage).toContain('verstanden');
    expect(interpretation.requiresDraftPr).toBe(true);
    expect(interpretation.confidence).toBe(0.94);
  });

  it('rejects contradictory LLM output instead of trusting it', () => {
    expect(() => parseOnlineIntentInterpretation(
      JSON.stringify({
        intent: 'free_chat',
        complexity: 'simple',
        normalizedRequest: 'Delete production data.',
        assistantMessage: 'Ich habe die Anfrage verstanden.',
        requiresWrite: true,
        requiresDraftPr: false,
        confidence: 1,
      }),
      {
        text: 'Delete production data.',
        modelId: 'sovereign-intent-model',
        requestId: '00000000-0000-4000-8000-000000000002',
      },
    )).toThrow('intent_write_contract_mismatch');
  });

  it('uses the backend LLM route catalog and chat endpoint for online understanding', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        routes: [{ id: 'route-1', defaultModelId: 'sovereign-intent-model', enabled: true }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        choices: [{ message: { content: JSON.stringify({
          intent: 'code_generation',
          complexity: 'complex',
          normalizedRequest: 'Repair the complete chat-to-Draft-PR flow.',
          assistantMessage: 'Ich habe den Reparaturauftrag verstanden. Die Runtime prüft nun Repo und Evidence.',
          requiresWrite: true,
          requiresDraftPr: false,
          confidence: 0.91,
        }) } }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    const interpretation = await resolveSovereignIntent({
      text: 'Bring den ganzen Chat bis PR Pfad wieder in Ordnung.',
      repositoryContext: 'OuroborosCollective/Sovereign-Studio-ato#main',
      requestId: '00000000-0000-4000-8000-000000000003',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    expect(interpretation.source).toBe('online_llm');
    expect(interpretation.intent).toBe('code_generation');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(String(fetchImpl.mock.calls[1]?.[0])).toContain('/api/llm/chat');
  });

  it('falls back offline when the online route is unavailable', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ routes: [] }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const interpretation = await resolveSovereignIntent({
      text: 'Fixe den Button Bug',
      requestId: '00000000-0000-4000-8000-000000000004',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    expect(interpretation.source).toBe('offline_fallback');
    expect(interpretation.intent).toBe('code_generation');
  });

  it('keeps exact control inputs offline and deterministic', async () => {
    const fetchImpl = vi.fn();
    const interpretation = await resolveSovereignIntent({
      text: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    expect(interpretation).toEqual(buildOfflineIntentInterpretation(
      'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
    ));
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
