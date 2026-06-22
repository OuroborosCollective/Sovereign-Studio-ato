import { callPollinations } from '../../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';

export function createPollinationsAdapter(): LlmAdapter {
  return {
    id: 'pollinations',
    label: 'Pollinations free provider',
    kind: 'no-key',
    priority: 1,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      // Build prompt with memory context and runtime information
      const prompt = buildSovereignLlmPrompt(context);
      
      try {
        const response = await callPollinations(
          'openai',
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 }
        );
        
        // Parse and validate the response
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