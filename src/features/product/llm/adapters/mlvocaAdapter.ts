import { callMlvoCa } from '../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

export function createMlvocaAdapter(): LlmAdapter {
  return {
    id: 'mlvoca',
    label: 'Mlvoca free provider',
    kind: 'no-key',
    priority: 0,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const response = await callMlvoCa(
          'deepseek-r1:1.5b',
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 },
        );

        const parsed = parseSovereignBrainJson(response.text);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('mlvoca', context.mission, parsed);

        return {
          providerId: 'mlvoca',
          brain: parsed,
          raw: response.text,
        };
      } catch (error) {
        throw new Error(`MLVOCA provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    },
  };
}
