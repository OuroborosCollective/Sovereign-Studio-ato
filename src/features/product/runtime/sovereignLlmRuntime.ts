import type { SovereignBrainResult } from '../brain/sovereignBrainContract';
import { resolveProductWithLlmRevolver } from '../llm/productLlmRevolver';
import { buildSovereignLlmPrompt as buildAdapterSovereignLlmPrompt } from '../llm/llmAdapter';
import { defaultSettings, starterCards } from '../constants';
import type { Card, ProjectSettings } from '../types';
import type { LlmRevolverFailure, LlmRevolverConsentRequired } from '../llm/llmAdapter';

export interface SovereignLlmRuntimeInput {
  mission: string;
  repoPaths: string[];
  selectedFilePath: string;
  previousPreview?: string;
  memoryContext: string[];
  runtimeEvents: string[];
  allowUserKeyRoutes?: boolean;
  allowExternalNoKey?: boolean;
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
  consentRequired?: boolean;
}

function userKeysWhenAllowed(input: SovereignLlmRuntimeInput): SovereignLlmRuntimeInput['userKeys'] {
  return input.allowUserKeyRoutes ? input.userKeys : undefined;
}

function lastTryingAttemptIndex(attempts: SovereignLlmRuntimeAttempt[], providerId?: string): number {
  for (let index = attempts.length - 1; index >= 0; index -= 1) {
    const attempt = attempts[index];
    if (attempt.providerId === providerId && attempt.status === 'trying') return index;
  }
  return -1;
}

export async function runSovereignLlmRuntime(input: SovereignLlmRuntimeInput): Promise<SovereignLlmRuntimeResult> {
  const attempts: SovereignLlmRuntimeAttempt[] = [];
  const allowedUserKeys = userKeysWhenAllowed(input);

  const result = await resolveProductWithLlmRevolver({
    mission: input.mission,
    repoPaths: input.repoPaths,
    selectedFilePath: input.selectedFilePath,
    cards: input.cards ?? starterCards(),
    settings: input.settings ?? defaultSettings,
    codeContext: input.previousPreview,
    memoryContext: input.memoryContext,
    runtimeEvents: input.runtimeEvents,
    pollinationsApiKey: allowedUserKeys?.pollinations,
    groqApiKey: allowedUserKeys?.groq,
    huggingfaceApiKey: allowedUserKeys?.huggingface,
    togetherApiKey: allowedUserKeys?.together,
    openrouterApiKey: allowedUserKeys?.openrouter,
    geminiApiKey: allowedUserKeys?.gemini,
    allowExternalNoKey: input.allowExternalNoKey ?? false,
    allowOptInRoutes: false,
  }, {
    onEvent: (event) => {
      if (event.type === 'provider:trying') {
        attempts.push({
          providerId: event.providerId ?? 'unknown',
          status: 'trying',
          message: event.message,
        });
        return;
      }

      if (event.type === 'provider:success' || event.type === 'provider:failed') {
        const index = lastTryingAttemptIndex(attempts, event.providerId);
        const nextStatus = event.type === 'provider:success' ? 'success' : 'failed';
        if (index >= 0) {
          attempts[index] = {
            ...attempts[index],
            status: nextStatus,
            message: event.message,
          };
          return;
        }

        attempts.push({
          providerId: event.providerId ?? 'unknown',
          status: nextStatus,
          message: event.message,
        });
        return;
      }

      if (event.type === 'provider:skipped') {
        attempts.push({
          providerId: event.providerId ?? 'unknown',
          status: 'skipped',
          message: event.message,
        });
      }
    },
  });

  if (result.ok) {
    return {
      ok: true,
      source: result.result.providerId === 'local-safe' ? 'local-safe' : 'llm-revolver',
      providerId: result.result.providerId,
      brain: result.result.brain,
      raw: result.result.raw,
      attempts,
    };
  }

  // Check for consent required state
  if ('consentRequired' in result && result.consentRequired) {
    return {
      ok: false,
      source: 'local-safe',
      providerId: 'local-safe',
      attempts,
      consentRequired: true,
      error: 'External no-key routes are blocked. User consent required to enable.',
    };
  }

  const failed = result as LlmRevolverFailure;
  return {
    ok: false,
    source: 'local-safe',
    providerId: 'local-safe',
    attempts,
    error: failed.failure.message,
  };
}

export function buildSovereignLlmPrompt(input: SovereignLlmRuntimeInput): string {
  return buildAdapterSovereignLlmPrompt({
    mission: input.mission,
    repoPaths: input.repoPaths,
    selectedFilePath: input.selectedFilePath,
    codeContext: input.previousPreview,
    allowExternalNoKey: input.allowExternalNoKey ?? false,
    memoryContext: input.memoryContext,
    runtimeEvents: input.runtimeEvents,
  });
}
