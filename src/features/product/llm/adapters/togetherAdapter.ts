import { callTogether } from '../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

export function createTogetherAdapter(apiKey: string): LlmAdapter {
  return {
    id: 'together',
    label: 'Together AI provider',
    kind: 'user-key',
    priority: 4,
    enabled: !!apiKey,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const response = await callTogether(
          apiKey,
          'meta-llama/Llama-3.2-1B-Instruct-Turbo',
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 },
        );

        const parsed = parseSovereignBrainJson(response.text);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('together', context.mission, parsed);

        return {
          providerId: 'together',
          brain: parsed,
          raw: response.text,
        };
      } catch (error) {
        throw new Error(`Together provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    },
  };
}
