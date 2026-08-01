import { callOpenRouter } from '../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

/**
 * Paid OpenRouter adapter — uses a capable paid-tier model when the caller
 * supplies their own API key.  This path is intentionally separate from the
 * free keyless revolver adapters (mlvoca, pollinations, ovh, hfPublicSpace,
 * puterJs).  Never hardcode the :free suffix here; that would silently route a
 * paid-key user through the free tier.
 *
 * Model selection rationale:
 *  • deepseek/deepseek-r1-0528   — state-of-the-art reasoning for code; free
 *    quota on OpenRouter with a key, paid tier lifts rate limits significantly.
 *  • Fallback model is intentionally NOT a :free variant to preserve the paid
 *    path semantics.
 */
const PAID_MODEL = 'deepseek/deepseek-r1-0528';

export function createOpenRouterAdapter(apiKey: string): LlmAdapter {
  return {
    id: 'openrouter',
    label: 'OpenRouter (paid-path)',
    kind: 'user-key',
    priority: 5,
    enabled: !!apiKey,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const response = await callOpenRouter(
          apiKey,
          PAID_MODEL,
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 },
        );

        const parsed = parseSovereignBrainJson(response.text);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('openrouter', context.mission, parsed);

        return {
          providerId: 'openrouter',
          brain: parsed,
          raw: response.text,
        };
      } catch (error) {
        throw new Error(
          `OpenRouter paid-path provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`,
        );
      }
    },
  };
}
