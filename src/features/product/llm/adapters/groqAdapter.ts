import { callGroq } from '../../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

export function createGroqAdapter(apiKey: string): LlmAdapter {
  return {
    id: 'groq',
    label: 'Groq API provider',
    kind: 'user-key',
    priority: 2,
    enabled: !!apiKey,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      // Build prompt with memory context and runtime information
      const prompt = buildSovereignLlmPrompt(context);
      
      try {
        const response = await callGroq(
          apiKey,
          'llama-3.1-8b-instant',
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 }
        );
        
        // Parse and validate the response
        const parsed = parseSovereignBrainJson(response.text);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('groq', context.mission, parsed);
        
        return {
          providerId: 'groq',
          brain: parsed,
          raw: response.text,
        };
      } catch (error) {
        throw new Error(`Groq provider failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    },
  };
}