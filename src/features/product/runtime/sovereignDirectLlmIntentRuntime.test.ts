import { describe, expect, it, vi } from 'vitest';
import { fetchSovereignDirectLlmInterpretation } from './sovereignDirectLlmIntentRuntime';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('sovereignDirectLlmIntentRuntime route binding', () => {
  it('fails closed when a manually pinned route is absent from the current catalog', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      routes: [{
        id: 'current-route',
        defaultModelId: 'openai/gpt-current',
        enabled: true,
        provider: 'openrouter',
        billingCategory: 'standard',
        fundingMode: 'provider_priced',
      }],
    })) as unknown as typeof fetch;

    const result = await fetchSovereignDirectLlmInterpretation({
      preferredModel: 'manually-pinned-route-that-disappeared',
      text: 'Prüfe den aktuellen Stand.',
      fetchImpl,
      requestId: '11111111-1111-4111-8111-111111111111',
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('Keine aktivierte OpenRouter- oder FreeLLM-Route');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
