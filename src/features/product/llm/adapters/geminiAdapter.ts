import { callGemini } from '../../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../../llmRuntimeChecks';
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
      // Build prompt with memory context and runtime information
      const prompt = buildSovereignLlmPrompt(context);
      
      try {
        const response = await callGemini(
          apiKey,
          'gemini-1.5-flash',
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 }
        );
        
        // Parse and validate the response
        const parsed = parseSovereignBrainJson(response.text);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('gemini', context.mission, parsed);
        
        return {
          providerId: 'gemini',
          brain: parsed,
          raw: response.text,
        };
      } catch (error) {
        throw new Error(`Gemini provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    },
  };
}