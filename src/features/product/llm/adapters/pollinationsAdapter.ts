import { callPollinations } from '../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

export function createPollinationsAdapter(apiKey?: string): LlmAdapter {
  return {
    id: 'pollinations',
    label: 'Pollinations free/provider API',
    kind: apiKey ? 'user-key' : 'no-key',
    priority: 1,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const response = await callPollinations(
          'openai',
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 },
          apiKey,
        );

        const parsed = parseSovereignBrainJson(response.text);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('pollinations', context.mission, parsed);

        return {
          providerId: 'pollinations',
          brain: parsed,
          raw: response.text,
        };
      } catch (error) {
        throw new Error(`Pollinations provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    },
  };
}
