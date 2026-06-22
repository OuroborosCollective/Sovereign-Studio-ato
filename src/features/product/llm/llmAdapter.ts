import type { SovereignBrainResult } from '../brain/sovereignBrainContract';

export type LlmProviderId =
  | 'mlvoca'
  | 'pollinations'
  | 'groq'
  | 'huggingface'
  | 'together'
  | 'openrouter'
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
