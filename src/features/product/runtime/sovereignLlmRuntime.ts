import type { SovereignBrainResult } from '../brain/sovereignBrainContract';
import { assertSovereignBrainResult, parseSovereignBrainJson } from '../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llm/llmRuntimeChecks';
import { callMlvoCa, callPollinations, callGroq, callHuggingFace, callTogether, callOpenRouter, providerManager } from '../../ai/providerManager';
import type { ExternalMemorySyncConfig } from './externalMemorySync';
import type { SolutionPatternStore } from './solutionPatternMemory';

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

// Provider order constants
const REQUIRED_PROVIDER_ORDER = [
  'mlvoca',
  'pollinations',
  'groq',
  'huggingface',
  'together',
  'openrouter',
  'gemini',
  'local-safe',
] as const;

const DEFAULT_PROVIDER_MODELS = {
  mlvoca: 'deepseek-r1:1.5b',
  pollinations: 'openai',
  groq: 'llama-3.1-8b-instant',
  huggingface: 'meta-llama/Llama-3.2-1B-Instruct',
  together: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
  openrouter: 'meta-llama/llama-3.1-8b-instruct:free',
  gemini: 'gemini-1.5-flash',
} as const;

const DEFAULT_LLM_OPTIONS = {
  temperature: 0.2,
  maxOutputTokens: 4096,
  stream: false,
  timeoutMs: 10_000,
} as const;

export function buildSovereignLlmPrompt(input: SovereignLlmRuntimeInput): string {
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
    input.mission,
    '',
    'SELECTED FILE:',
    input.selectedFilePath,
    '',
    'REMOTE MEMORY CONTEXT:',
    input.memoryContext.join('\n') || 'none',
    '',
    'RUNTIME EVENTS:',
    input.runtimeEvents.join('\n') || 'none',
    '',
    'REPOSITORY PATHS:',
    input.repoPaths.slice(0, 220).join('\n') || 'none',
  ].join('\n');
}

/**
 * Try to parse and validate LLM response as SovereignBrainResult
 */
function tryParseBrainResult(raw: string): SovereignBrainResult | null {
  try {
    const parsed = parseSovereignBrainJson(raw);
    assertSovereignBrainResult(parsed);
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Run LLM with a specific provider
 */
async function runProvider(
  providerId: string,
  prompt: string,
  input: SovereignLlmRuntimeInput
): Promise<{ brain: SovereignBrainResult; raw: string; model?: string } | null> {
  try {
    let response: { text: string; provider: string; model?: string };
    
    switch (providerId) {
      case 'mlvoca':
        response = await callMlvoCa(
          DEFAULT_PROVIDER_MODELS.mlvoca,
          prompt,
          DEFAULT_LLM_OPTIONS
        );
        break;
        
      case 'pollinations':
        response = await callPollinations(
          DEFAULT_PROVIDER_MODELS.pollinations,
          prompt,
          DEFAULT_LLM_OPTIONS,
          input.userKeys?.pollinations
        );
        break;
        
      case 'groq':
        if (!input.allowUserKeyRoutes || !input.userKeys?.groq) {
          throw new Error('Groq API key required');
        }
        response = await callGroq(
          input.userKeys.groq,
          DEFAULT_PROVIDER_MODELS.groq,
          prompt,
          DEFAULT_LLM_OPTIONS
        );
        break;
        
      case 'huggingface':
        if (!input.allowUserKeyRoutes || !input.userKeys?.huggingface) {
          throw new Error('HuggingFace API key required');
        }
        response = await callHuggingFace(
          input.userKeys.huggingface,
          DEFAULT_PROVIDER_MODELS.huggingface,
          prompt,
          DEFAULT_LLM_OPTIONS
        );
        break;
        
      case 'together':
        if (!input.allowUserKeyRoutes || !input.userKeys?.together) {
          throw new Error('Together API key required');
        }
        response = await callTogether(
          input.userKeys.together,
          DEFAULT_PROVIDER_MODELS.together,
          prompt,
          DEFAULT_LLM_OPTIONS
        );
        break;
        
      case 'openrouter':
        if (!input.allowUserKeyRoutes || !input.userKeys?.openrouter) {
          throw new Error('OpenRouter API key required');
        }
        response = await callOpenRouter(
          input.userKeys.openrouter,
          DEFAULT_PROVIDER_MODELS.openrouter,
          prompt,
          DEFAULT_LLM_OPTIONS
        );
        break;
        
      case 'gemini':
        if (!input.allowUserKeyRoutes || !input.userKeys?.gemini) {
          throw new Error('Gemini API key required');
        }
        // Use providerManager for Gemini
        response = await providerManager.generateWithFallback(
          input.userKeys.gemini,
          'gemini',
          prompt,
          DEFAULT_LLM_OPTIONS
        );
        break;
        
      default:
        throw new Error(`Unknown provider: ${providerId}`);
    }

    const brain = tryParseBrainResult(response.text);
    if (!brain) {
      throw new Error('Invalid brain result format');
    }

    // Validate the brain result
    assertPushableBrain(providerId as any, input.mission, brain);

    return {
      brain,
      raw: response.text,
      model: response.model
    };
  } catch (error) {
    return null;
  }
}

/**
 * Run the sovereign LLM runtime with fallback chain
 */
export async function runSovereignLlmRuntime(input: SovereignLlmRuntimeInput): Promise<SovereignLlmRuntimeResult> {
  const attempts: SovereignLlmRuntimeAttempt[] = [];
  const prompt = buildSovereignLlmPrompt(input);

  // Build provider chain - free providers first, then user key providers if allowed
  const providerChain: string[] = ['mlvoca', 'pollinations'];
  
  if (input.allowUserKeyRoutes) {
    // Add user key providers if keys are provided
    if (input.userKeys?.groq) providerChain.push('groq');
    if (input.userKeys?.huggingface) providerChain.push('huggingface');
    if (input.userKeys?.together) providerChain.push('together');
    if (input.userKeys?.openrouter) providerChain.push('openrouter');
    if (input.userKeys?.gemini) providerChain.push('gemini');
  }

  // Try each provider in order
  for (const providerId of providerChain) {
    attempts.push({
      providerId,
      status: 'trying',
      message: `Trying ${providerId} provider.`
    });

    try {
      const result = await runProvider(providerId, prompt, input);
      
      if (result) {
        attempts[attempts.length - 1] = {
          providerId,
          model: result.model,
          status: 'success',
          message: `${providerId} returned valid brain result.`
        };

        return {
          ok: true,
          source: 'llm-revolver',
          providerId,
          model: result.model,
          brain: result.brain,
          raw: result.raw,
          attempts,
        };
      } else {
        attempts[attempts.length - 1] = {
          providerId,
          status: 'failed',
          message: `${providerId} returned invalid or no result.`
        };
      }
    } catch (error) {
      attempts[attempts.length - 1] = {
        providerId,
        status: 'failed',
        message: `${providerId} failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }

  // All providers failed
  return {
    ok: false,
    source: 'local-safe',
    providerId: 'local-safe',
    attempts,
    error: 'All LLM providers failed. Falling back to local safe mode.'
  };
}