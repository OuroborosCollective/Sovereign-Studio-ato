import { geminiService } from '../../../ai/geminiService';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

export function createGeminiAdapter(apiKey: string): LlmAdapter {
  return {
    id: 'gemini',
    label: 'Google Gemini API provider',
    kind: 'user-key',
    priority: 6,
    enabled: !!apiKey,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const raw = await geminiService.generateText(apiKey, prompt, {
          model: 'gemini-1.5-flash',
          temperature: 0.2,
          maxOutputTokens: 4096,
        });

        const parsed = parseSovereignBrainJson(raw);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('gemini', context.mission, parsed);

        return {
          providerId: 'gemini',
          brain: parsed,
          raw,
        };
      } catch (error) {
        throw new Error(`Gemini provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    },
  };
}
