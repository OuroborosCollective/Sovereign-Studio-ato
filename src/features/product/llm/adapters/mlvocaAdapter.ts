import { callMlvoCa } from '../../../../ai/providerManager';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';

export function buildSovereignLlmPrompt(context: LlmAdapterContext): string {
  return [
    'You are the LLM runtime of Sovereign Studio, a no-code repository automation tool.',
    'Return ONLY valid JSON matching the SovereignBrainResult TypeScript interface.',
    'Do not return markdown.',
    'Do not explain outside JSON.',
    'The user may use vague natural language. Normalize it into concrete repository work.',
    'Use repository paths, runtime events and memory context.',
    'execution.patches is mandatory.',
    'Each patch must include: file, type, description, code.',
    'Allowed patch types: replace, insert, delete, create.',
    'Do not return plan-only output.',
    'Do not touch .env, credentials, private keys, node_modules, dist or build output.',
    'Prefer real changes in src/, tests/, android/, scripts/, .github/workflows/, README.md or docs/.',
    'Runtime guards are authoritative. Your output will be rejected if it violates them.',
    '',
    'USER MISSION:',
    context.mission,
    '',
    'SELECTED FILE:',
    context.selectedFilePath,
    '',
    'REMOTE MEMORY CONTEXT:',
    (context as any).memoryContext?.join('\n') || 'none',
    '',
    'RUNTIME EVENTS:',
    (context as any).runtimeEvents?.join('\n') || 'none',
    '',
    'REPOSITORY PATHS:',
    context.repoPaths.slice(0, 220).join('\n') || 'none',
  ].join('\n');
}

export function createMlvocaAdapter(): LlmAdapter {
  return {
    id: 'mlvoca',
    label: 'Mlvoca free provider',
    kind: 'no-key',
    priority: 0,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      // Build prompt with memory context and runtime information
      const prompt = buildSovereignLlmPrompt(context);
      
      try {
        const response = await callMlvoCa(
          'deepseek-r1:1.5b',
          prompt,
          { temperature: 0.2, maxOutputTokens: 4096 }
        );
        
        // Parse and validate the response
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