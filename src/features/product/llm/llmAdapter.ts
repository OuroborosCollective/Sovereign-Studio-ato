import type { SovereignBrainResult } from '../brain/sovereignBrainContract';

export type LlmProviderId =
  | 'mlvoca'
  | 'pollinations'
  | 'groq'
  | 'huggingface'
  | 'together'
  | 'openrouter'
  | 'gemini'
  | 'optional-user-keys'
  | 'ovh-anonymous-code-chat'
  | 'ovh-anonymous-fixed-model'
  | 'puter-js-opt-in'
  | 'hf-curated-public-space'
  | 'local-safe';

export type LlmProviderKind = 'existing' | 'no-key' | 'user-key' | 'opt-in' | 'local-safe';

export type LlmFailureCode =
  | 'rate_limit'
  | 'unauthorized'
  | 'timeout'
  | 'network'
  | 'invalid_contract'
  | 'empty_output'
  | 'disabled'
  | 'unknown';

export interface LlmAdapterContext {
  mission: string;
  repoPaths: string[];
  selectedFilePath: string;
  codeContext?: string;
  logs?: string[];
  allowExternalNoKey?: boolean;
  allowOptInRoutes?: boolean;
  signal?: AbortSignal;
  memoryContext?: string[];
  runtimeEvents?: string[];
}

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
    context.memoryContext?.join('\n') || 'none',
    '',
    'RUNTIME EVENTS:',
    context.runtimeEvents?.join('\n') || 'none',
    '',
    'REPOSITORY PATHS:',
    context.repoPaths.slice(0, 220).join('\n') || 'none',
  ].join('\n');
}

export interface LlmAdapterResult {
  providerId: LlmProviderId;
  brain: SovereignBrainResult;
  raw?: string;
}

export interface LlmAdapterFailure {
  providerId: LlmProviderId;
  code: LlmFailureCode;
  message: string;
  retryable: boolean;
  status?: number;
}

export interface LlmAdapter {
  id: LlmProviderId;
  label: string;
  kind: LlmProviderKind;
  priority: number;
  enabled: boolean;
  run(context: LlmAdapterContext): Promise<LlmAdapterResult>;
}

export interface LlmRevolverEvent {
  type: 'provider:trying' | 'provider:success' | 'provider:failed' | 'provider:skipped' | 'revolver:exhausted';
  providerId?: LlmProviderId;
  message: string;
  code?: LlmFailureCode;
  attempt: number;
}

export interface LlmRevolverMemory {
  nextIndex: number;
  shots: Array<{
    providerId: LlmProviderId;
    code?: LlmFailureCode;
    at: number;
  }>;
}

export interface LlmRevolverOptions {
  memory?: LlmRevolverMemory;
  maxShots?: number;
  now?: () => number;
  onEvent?: (event: LlmRevolverEvent) => void;
}

export interface LlmRevolverSuccess {
  ok: true;
  result: LlmAdapterResult;
  memory: LlmRevolverMemory;
  attempts: LlmRevolverEvent[];
}

export interface LlmRevolverFailure {
  ok: false;
  failure: LlmAdapterFailure;
  memory: LlmRevolverMemory;
  attempts: LlmRevolverEvent[];
}

export type LlmRevolverResult = LlmRevolverSuccess | LlmRevolverFailure;

export function createInitialRevolverMemory(): LlmRevolverMemory {
  return { nextIndex: 0, shots: [] };
}
