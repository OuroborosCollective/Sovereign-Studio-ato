import { callHuggingFace } from '../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

export function createHuggingFaceAdapter(apiKey: string): LlmAdapter {
  return {
    id: 'huggingface',
    label: 'HuggingFace API provider',
    kind: 'user-key',
    priority: 3,
    enabled: !!apiKey,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const response = await callHuggingFace(
          apiKey,
          'meta-llama/Llama-3.2-1B-Instruct',
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 },
        );

        const parsed = parseSovereignBrainJson(response.text);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('huggingface', context.mission, parsed);

        return {
          providerId: 'huggingface',
          brain: parsed,
          raw: response.text,
        };
      } catch (error) {
        throw new Error(`HuggingFace provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    },
  };
}
