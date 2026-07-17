import { freeFirstProviderRoute } from '../freeFirstPlan';
import type { LlmProviderId } from './llmAdapter';

export const LLM_FALLBACK_ORDER: LlmProviderId[] = [
  'local-safe',
];

export function orderedProviderIds(): LlmProviderId[] {
  return [...freeFirstProviderRoute, ...LLM_FALLBACK_ORDER];
}
