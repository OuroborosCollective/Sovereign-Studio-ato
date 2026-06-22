import { callOpenRouter } from '../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

export function createOpenRouterAdapter(apiKey: string): LlmAdapter {
  return {
    id: 'openrouter',
    label: 'OpenRouter API provider',
    kind: 'user-key',
    priority: 5,
    enabled: !!apiKey,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const response = await callOpenRouter(
          apiKey,
          'meta-llama/llama-3.1-8b-instruct:free',
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
        throw new Error(`OpenRouter provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    },
  };
}
