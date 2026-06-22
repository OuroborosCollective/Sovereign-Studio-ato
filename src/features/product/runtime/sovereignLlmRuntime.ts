import type { SovereignBrainResult } from '../brain/sovereignBrainContract';
import { resolveProductWithLlmRevolver } from '../llm/productLlmRevolver';
import { defaultSettings, starterCards } from '../constants';
import type { Card, ProjectSettings } from '../types';

export interface SovereignLlmRuntimeInput {
  mission: string;
  repoPaths: string[];
  selectedFilePath: string;
  previousPreview?: string;
  memoryContext: string[];
  runtimeEvents: string[];
  allowUserKeyRoutes?: boolean;
  userKeys?: {
    gemini?: string;
    groq?: string;
    huggingface?: string;
    together?: string;
    openrouter?: string;
    pollinations?: string;
  };
  signal?: AbortSignal;
  cards?: Card[];
  settings?: ProjectSettings;
}

export interface SovereignLlmRuntimeAttempt {
  providerId: string;
  model?: string;
  status: 'trying' | 'success' | 'failed' | 'skipped';
  message: string;
}

export interface SovereignLlmRuntimeResult {
  ok: boolean;
  source: 'llm-revolver' | 'local-safe';
  providerId: string;
  model?: string;
  brain?: SovereignBrainResult;
  raw?: string;
  attempts: SovereignLlmRuntimeAttempt[];
  error?: string;
}

/**
 * Run the sovereign LLM runtime with fallback chain using the existing revolver
 */
export async function runSovereignLlmRuntime(input: SovereignLlmRuntimeInput): Promise<SovereignLlmRuntimeResult> {
  // Convert our attempt tracking to the revolver event system
  const attempts: SovereignLlmRuntimeAttempt[] = [];
  
  const result = await resolveProductWithLlmRevolver({
    mission: input.mission,
    repoPaths: input.repoPaths,
    selectedFilePath: input.selectedFilePath,
    cards: input.cards ?? starterCards(),
    settings: input.settings ?? defaultSettings,
    memoryContext: input.memoryContext,
    runtimeEvents: input.runtimeEvents,
    pollinationsApiKey: input.userKeys?.pollinations,
    groqApiKey: input.userKeys?.groq,
    huggingfaceApiKey: input.userKeys?.huggingface,
    togetherApiKey: input.userKeys?.together,
    openrouterApiKey: input.userKeys?.openrouter,
    geminiApiKey: input.userKeys?.gemini,
    allowExternalNoKey: input.allowUserKeyRoutes,
  }, {
    onEvent: (event) => {
      // Convert revolver events to our attempt tracking
      switch (event.type) {
        case 'provider:trying':
          attempts.push({
            providerId: event.providerId!,
            status: 'trying',
            message: event.message,
          });
          break;
        case 'provider:success':
          // Update the last attempt
          if (attempts.length > 0) {
            const lastAttempt = attempts[attempts.length - 1];
            if (lastAttempt.providerId === event.providerId) {
              attempts[attempts.length - 1] = {
                ...lastAttempt,
                status: 'success',
                message: event.message,
              };
            }
          }
          break;
        case 'provider:failed':
          // Update the last attempt
          if (attempts.length > 0) {
            const lastAttempt = attempts[attempts.length - 1];
            if (lastAttempt.providerId === event.providerId) {
              attempts[attempts.length - 1] = {
                ...lastAttempt,
                status: 'failed',
                message: event.message,
              };
            }
          }
          break;
        case 'provider:skipped':
          attempts.push({
            providerId: event.providerId!,
            status: 'skipped',
            message: event.message,
          });
          break;
      }
    }
  });

  if (result.ok) {
    return {
      ok: true,
      source: 'llm-revolver',
      providerId: result.result.providerId,
      brain: result.result.brain,
      raw: result.result.raw,
      attempts,
    };
  } else {
    return {
      ok: false,
      source: 'local-safe',
      providerId: 'local-safe',
      attempts,
      error: result.failure.message,
    };
  }
}

export function buildSovereignLlmPrompt(input: any): string {
  // This is now handled by the adapters, but kept for backward compatibility
  return '';
}