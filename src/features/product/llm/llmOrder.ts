import { freeFirstProviderRoute } from '../freeFirstPlan';
import type { LlmProviderId } from './llmAdapter';

export const LLM_FALLBACK_ORDER: LlmProviderId[] = [
  'ovh-anonymous-code-chat',
  'ovh-anonymous-fixed-model',
  'puter-js-opt-in',
  'hf-curated-public-space',
  'local-safe',
];

export function orderedProviderIds(): LlmProviderId[] {
  return [...freeFirstProviderRoute, ...LLM_FALLBACK_ORDER];
}
