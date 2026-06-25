/**
 * Chat Runtime
 *
 * Entry -> Process -> Exit data flow for chat diagnostics.
 * The official live user path is the BuilderContainer NoCode Chat Workbench.
 * This runtime is deliberately honest: it validates input and may call an
 * explicitly supplied processor, but it never fabricates LLM/OpenHands output.
 */

import { defaultTraceIdProvider, globalTelemetry, runtimeIntelligence } from '../../../runtime/RuntimeIntelligence';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface ChatSuggestion {
  id: string;
  title: string;
  description?: string;
  action: string;
  accepted: boolean;
  priority?: number;
}

export interface ChatEntryValidation {
  valid: boolean;
  normalizedInput: string;
  errors: string[];
  sanitized: boolean;
}

export interface ChatProcessResult {
  success: boolean;
  response?: string;
  modelUsed?: string;
  latencyMs?: number;
  error?: string;
  guardResults?: string[];
}

export interface ChatExitState {
  messages: ChatMessage[];
  suggestions: ChatSuggestion[];
  lastMessage?: ChatMessage;
  modelHealth: {
    status: 'healthy' | 'degraded' | 'unknown';
    latencyMs: number | null;
    modelId: string | null;
  };
  openHandsStatus: {
    status: 'idle' | 'running' | 'completed' | 'failed';
    jobId?: string;
  };
}

export interface ChatRuntimeModelRef {
  modelId: string;
  modelName: string;
  latencyMs: number | null;
}

export type ChatRuntimeProcessor = (input: {
  normalizedInput: string;
  history: ChatMessage[];
  model: ChatRuntimeModelRef;
}) => Promise<{ response: string; modelUsed?: string }>;

export interface ChatRuntimeConfig {
  maxMessageLength?: number;
  minMessageLength?: number;
  checkModelHealth?: boolean;
  enableOpenHands?: boolean;
  responseTimeoutMs?: number;
  processor?: ChatRuntimeProcessor;
}

const DEFAULT_CONFIG: Required<Omit<ChatRuntimeConfig, 'processor'>> = {
  maxMessageLength: 10000,
  minMessageLength: 1,
  checkModelHealth: true,
  enableOpenHands: true,
  responseTimeoutMs: 30000,
};

function mergedConfig(config: ChatRuntimeConfig): Required<Omit<ChatRuntimeConfig, 'processor'>> & Pick<ChatRuntimeConfig, 'processor'> {
  return { ...DEFAULT_CONFIG, processor: config.processor };
}

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now();
}

function traceId(): string {
  return defaultTraceIdProvider();
}

export function validateChatEntry(input: string, config: ChatRuntimeConfig = {}): ChatEntryValidation {
  const cfg = mergedConfig(config);
  const errors: string[] = [];
  const normalized = input.trim();
  const sanitized = normalized.replace(/[<>]/g, '').replace(/\0/g, '');

  if (normalized.length < cfg.minMessageLength) errors.push(`Message too short (min: ${cfg.minMessageLength} chars)`);
  if (normalized.length > cfg.maxMessageLength) errors.push(`Message too long (max: ${cfg.maxMessageLength} chars)`);

  globalTelemetry.track({
    name: 'chat_entry_validated',
    properties: {
      inputLength: input.length,
      normalizedLength: normalized.length,
      sanitizedLength: sanitized.length,
      valid: errors.length === 0,
      errors,
    },
    timestamp: Date.now(),
    traceId: traceId(),
  });

  return {
    valid: errors.length === 0,
    normalizedInput: sanitized,
    errors,
    sanitized: sanitized !== normalized,
  };
}

export async function checkChatEntryGuard(_input: string): Promise<{ pass: boolean; reason?: string }> {
  try {
    const modelHealthResult = runtimeIntelligence.getModelHealthFallbackResult();
    if (!modelHealthResult.proceed) {
      return { pass: false, reason: `Model health check failed: ${modelHealthResult.reason}` };
    }

    const fallbackState = runtimeIntelligence.getModelHealthFallbackState();
    if (fallbackState.circuitBreaker.state === 'open') {
      return { pass: false, reason: 'Circuit breaker is open - too many model failures' };
    }

    return { pass: true };
  } catch (error) {
    return { pass: false, reason: error instanceof Error ? error.message : 'Guard check failed' };
  }
}

export function getChatModel(): ChatRuntimeModelRef | null {
  const model = runtimeIntelligence.getBestAvailableModel();
  if (model) return { modelId: model.id, modelName: model.name, latencyMs: model.latencyMs };

  const fallback = runtimeIntelligence.getModelHealthFallbackResult();
  if (fallback.selectedModel) {
    return {
      modelId: fallback.selectedModel.adapterId,
      modelName: fallback.selectedModel.adapterName,
      latencyMs: fallback.selectedModel.latencyMs,
    };
  }

  return null;
}

export async function processChatMessage(
  normalizedInput: string,
  history: ChatMessage[],
  config: ChatRuntimeConfig = {},
): Promise<ChatProcessResult> {
  const cfg = mergedConfig(config);
  const startTime = nowMs();

  try {
    const model = getChatModel();
    if (!model) return { success: false, error: 'No available model for processing' };

    globalTelemetry.track({
      name: 'chat_process_started',
      properties: { modelId: model.modelId, inputLength: normalizedInput.length, historyLength: history.length },
      timestamp: Date.now(),
      traceId: traceId(),
    });

    if (!cfg.processor) {
      return {
        success: false,
        error: 'No executable chat processor configured. Use the Builder Chat Workbench/OpenHands live path.',
        modelUsed: model.modelId,
        latencyMs: Math.round(nowMs() - startTime),
      };
    }

    const result = await Promise.race([
      cfg.processor({ normalizedInput, history, model }),
      new Promise<never>((_, reject) => {
        globalThis.setTimeout(() => reject(new Error('Chat processor timed out.')), Math.max(1, cfg.responseTimeoutMs));
      }),
    ]);

    const latencyMs = Math.round(nowMs() - startTime);
    runtimeIntelligence.recordModelSuccessForFallback(model.modelId);

    return {
      success: true,
      response: result.response,
      modelUsed: result.modelUsed ?? model.modelId,
      latencyMs,
    };
  } catch (error) {
    const latencyMs = Math.round(nowMs() - startTime);
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    const model = getChatModel();
    if (model) runtimeIntelligence.recordModelFailureForFallback(model.modelId);

    globalTelemetry.track({
      name: 'chat_process_error',
      properties: { error: errorMessage, latencyMs },
      timestamp: Date.now(),
      traceId: traceId(),
    });

    return { success: false, error: errorMessage, latencyMs };
  }
}

export function buildChatExitState(messages: ChatMessage[], result: ChatProcessResult, config: ChatRuntimeConfig = {}): ChatExitState {
  void config;
  const modelHealth = runtimeIntelligence.getModelHealthReport();
  const suggestions: ChatSuggestion[] = [];

  if (result.success && result.modelUsed) {
    suggestions.push({
      id: 'model-info',
      title: `${result.modelUsed} responded`,
      description: `Latency: ${result.latencyMs?.toFixed(0) ?? 'N/A'}ms`,
      action: 'info',
      accepted: false,
      priority: 1,
    });
  } else {
    suggestions.push({
      id: 'retry',
      title: 'Retry with the official Builder Chat Workbench',
      description: 'Live work must go through the runtime-backed OpenHands flow.',
      action: 'retry-builder-chat',
      accepted: false,
      priority: 10,
    });
  }

  globalTelemetry.track({
    name: 'chat_exit_state_built',
    properties: {
      messageCount: messages.length,
      suggestionCount: suggestions.length,
      success: result.success,
      modelHealth: modelHealth?.summary ?? 'none',
    },
    timestamp: Date.now(),
    traceId: traceId(),
  });

  return {
    messages,
    suggestions,
    lastMessage: messages.at(-1),
    modelHealth: {
      status: result.success ? 'healthy' : modelHealth?.healthyCount ? 'healthy' : 'unknown',
      latencyMs: result.latencyMs ?? null,
      modelId: result.modelUsed ?? null,
    },
    openHandsStatus: { status: 'idle' },
  };
}

export class ChatRuntimeError extends Error {
  constructor(
    message: string,
    public readonly stage: 'entry' | 'process' | 'exit',
    public readonly recoverable: boolean,
    public readonly context?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ChatRuntimeError';
  }
}

export function assertChatRuntimeHealthy(): void {
  const health = runtimeIntelligence.getRuntimeHealth();
  if (health.status === 'red') {
    throw new ChatRuntimeError(`Runtime health is red: ${health.reasons.join(', ')}`, 'process', false, { health });
  }

  const modelFallback = runtimeIntelligence.getModelHealthFallbackResult();
  if (!modelFallback.proceed) {
    throw new ChatRuntimeError(`Model health not ready: ${modelFallback.reason}`, 'process', true, { modelFallback });
  }
}

export async function executeChatRuntime(
  input: string,
  history: ChatMessage[],
  config: ChatRuntimeConfig = {},
): Promise<{ success: boolean; exitState?: ChatExitState; error?: ChatRuntimeError }> {
  const cfg = mergedConfig(config);
  const validation = validateChatEntry(input, cfg);

  if (!validation.valid) {
    return { success: false, error: new ChatRuntimeError(validation.errors.join(', '), 'entry', true, { validation }) };
  }

  const guardResult = await checkChatEntryGuard(input);
  if (!guardResult.pass) {
    return { success: false, error: new ChatRuntimeError(guardResult.reason ?? 'Entry guard failed', 'entry', true, { guardResult }) };
  }

  try {
    assertChatRuntimeHealthy();
    const processResult = await processChatMessage(validation.normalizedInput, history, cfg);
    return { success: processResult.success, exitState: buildChatExitState(history, processResult, cfg) };
  } catch (error) {
    return {
      success: false,
      error: new ChatRuntimeError(error instanceof Error ? error.message : 'Process failed', 'process', true, { error }),
    };
  }
}
