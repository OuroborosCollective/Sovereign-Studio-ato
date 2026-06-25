/**
 * Chat Runtime - Central Nervous System Contact Points
 * 
 * Entry → Process → Exit data flow with validation and error boundaries.
 * Connected to RuntimeIntelligence for telemetry, guards, and health.
 * 
 * Architecture:
 * ┌─────────────────────────────────────────────────────────────┐
 * │                    CHAT RUNTIME                          │
 * │  ┌─────────┐    ┌─────────────┐    ┌─────────┐           │
 * │  │  ENTRY  │───▶│   PROCESS  │───▶│  EXIT   │           │
 * │  │ Validation│   │ ModelHealth│    │ Render  │           │
 * │  │ Guard   │    │ OpenHands  │    │ State   │           │
 * │  └─────────┘    └─────────────┘    └─────────┘           │
 * │        │              │                │                  │
 * │        └──────────────┼────────────────┘                  │
 * │                       ▼                                   │
 * │              ┌─────────────────┐                         │
 * │              │ RuntimeIntelli. │                         │
 * │              │ - Telemetry     │                         │
 * │              │ - Health Snap   │                         │
 * │              │ - Circuit Brek │                         │
 * │              └─────────────────┘                         │
 * └─────────────────────────────────────────────────────────────┘
 */

import { runtimeIntelligence, globalTelemetry, RuntimeIntelligence } from '../../../runtime/RuntimeIntelligence';

// ============================================================================
// Types
// ============================================================================

/** Chat message type */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

/** Chat suggestion */
export interface ChatSuggestion {
  id: string;
  title: string;
  description?: string;
  action: string;
  accepted: boolean;
  priority?: number;
}

/** Entry validation result */
export interface ChatEntryValidation {
  valid: boolean;
  normalizedInput: string;
  errors: string[];
  sanitized: boolean;
}

/** Process result */
export interface ChatProcessResult {
  success: boolean;
  response?: string;
  modelUsed?: string;
  latencyMs?: number;
  error?: string;
  guardResults?: string[];
}

/** Exit state */
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

/** Chat runtime configuration */
export interface ChatRuntimeConfig {
  /** Maximum message length */
  maxMessageLength?: number;
  /** Minimum message length */
  minMessageLength?: number;
  /** Enable model health check */
  checkModelHealth?: boolean;
  /** Enable OpenHands integration */
  enableOpenHands?: boolean;
  /** Timeout for model response */
  responseTimeoutMs?: number;
}

const DEFAULT_CONFIG: Required<ChatRuntimeConfig> = {
  maxMessageLength: 10000,
  minMessageLength: 1,
  checkModelHealth: true,
  enableOpenHands: true,
  responseTimeoutMs: 30000,
};

// ============================================================================
// Entry Point - Validation
// ============================================================================

/**
 * Validate chat input at entry point
 */
export function validateChatEntry(
  input: string,
  config: ChatRuntimeConfig = {}
): ChatEntryValidation {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const errors: string[] = [];
  
  // Normalize input
  const normalized = input.trim();
  
  // Length validation
  if (normalized.length < cfg.minMessageLength) {
    errors.push(`Message too short (min: ${cfg.minMessageLength} chars)`);
  }
  
  if (normalized.length > cfg.maxMessageLength) {
    errors.push(`Message too long (max: ${cfg.maxMessageLength} chars)`);
  }
  
  // Sanitize input
  const sanitized = normalized
    .replace(/[<>]/g, '') // Remove potential HTML
    .replace(/\0/g, '');   // Remove null bytes
    
  // Log entry validation
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
    traceId: RuntimeIntelligence.createTraceId(),
  });
  
  return {
    valid: errors.length === 0,
    normalizedInput: sanitized,
    errors,
    sanitized: sanitized !== normalized,
  };
}

/**
 * Guard check at entry point
 */
export async function checkChatEntryGuard(input: string): Promise<{ pass: boolean; reason?: string }> {
  try {
    // Check model health
    const modelHealthResult = runtimeIntelligence.getModelHealthFallbackResult();
    
    if (!modelHealthResult.proceed) {
      return {
        pass: false,
        reason: `Model health check failed: ${modelHealthResult.reason}`,
      };
    }
    
    // Check circuit breaker
    const fallbackState = runtimeIntelligence.getModelHealthFallbackState();
    if (fallbackState.circuitBreaker.state === 'open') {
      return {
        pass: false,
        reason: 'Circuit breaker is open - too many model failures',
      };
    }
    
    return { pass: true };
  } catch (error) {
    return {
      pass: false,
      reason: error instanceof Error ? error.message : 'Guard check failed',
    };
  }
}

// ============================================================================
// Process - Model Health & OpenHands
// ============================================================================

/**
 * Get model for chat processing
 */
export function getChatModel(): { modelId: string; modelName: string; latencyMs: number | null } | null {
  const model = runtimeIntelligence.getBestAvailableModel();
  if (model) {
    return {
      modelId: model.id,
      modelName: model.name,
      latencyMs: model.latencyMs,
    };
  }
  
  // Fallback to cached model
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

/**
 * Process chat message through LLM
 */
export async function processChatMessage(
  normalizedInput: string,
  history: ChatMessage[],
  config: ChatRuntimeConfig = {}
): Promise<ChatProcessResult> {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const startTime = performance.now();
  
  try {
    // Get model
    const model = getChatModel();
    if (!model) {
      return {
        success: false,
        error: 'No available model for processing',
      };
    }
    
    // Build context from history
    const contextMessages = history.slice(-10).map(m => ({
      role: m.role,
      content: m.content,
    }));
    
    // Log process start
    globalTelemetry.track({
      name: 'chat_process_started',
      properties: {
        modelId: model.modelId,
        inputLength: normalizedInput.length,
        historyLength: history.length,
      },
      timestamp: Date.now(),
      traceId: RuntimeIntelligence.createTraceId(),
    });
    
    // Simulate processing (actual LLM call would go here)
    await new Promise(resolve => setTimeout(resolve, 100));
    
    const latencyMs = performance.now() - startTime;
    
    // Record success for fallback tracking
    runtimeIntelligence.recordModelSuccessForFallback(model.modelId);
    
    return {
      success: true,
      response: `Processed: ${normalizedInput.substring(0, 50)}...`,
      modelUsed: model.modelId,
      latencyMs,
    };
    
  } catch (error) {
    const latencyMs = performance.now() - startTime;
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    
    // Record failure for fallback tracking
    const model = getChatModel();
    if (model) {
      runtimeIntelligence.recordModelFailureForFallback(model.modelId);
    }
    
    // Log error
    globalTelemetry.track({
      name: 'chat_process_error',
      properties: {
        error: errorMessage,
        latencyMs,
      },
      timestamp: Date.now(),
      traceId: RuntimeIntelligence.createTraceId(),
    });
    
    return {
      success: false,
      error: errorMessage,
      latencyMs,
    };
  }
}

// ============================================================================
// Exit Point - State Building
// ============================================================================

/**
 * Build chat exit state
 */
export function buildChatExitState(
  messages: ChatMessage[],
  result: ChatProcessResult,
  config: ChatRuntimeConfig = {}
): ChatExitState {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  
  // Get model health
  const model = getChatModel();
  const modelHealth = runtimeIntelligence.getModelHealthReport();
  
  // Build suggestions based on result
  const suggestions: ChatSuggestion[] = [];
  
  if (result.success && result.modelUsed) {
    // Add model-specific suggestions
    suggestions.push({
      id: 'model-info',
      title: `${result.modelUsed} responded`,
      description: `Latency: ${result.latencyMs?.toFixed(0) ?? 'N/A'}ms`,
      action: 'info',
      accepted: false,
      priority: 1,
    });
  } else {
    // Add recovery suggestions
    suggestions.push({
      id: 'retry',
      title: 'Retry with different model',
      description: 'Try another available model',
      action: 'retry',
      accepted: false,
      priority: 10,
    });
  }
  
  // Log exit state
  globalTelemetry.track({
    name: 'chat_exit_state_built',
    properties: {
      messageCount: messages.length,
      suggestionCount: suggestions.length,
      success: result.success,
      modelHealth: modelHealth?.summary ?? 'none',
    },
    timestamp: Date.now(),
    traceId: RuntimeIntelligence.createTraceId(),
  });
  
  return {
    messages,
    suggestions,
    modelHealth: {
      status: result.success ? 'healthy' : modelHealth?.healthyCount ? 'healthy' : 'unknown',
      latencyMs: result.latencyMs ?? null,
      modelId: result.modelUsed ?? null,
    },
    openHandsStatus: {
      status: 'idle', // Would be connected to OpenHands state
    },
  };
}

// ============================================================================
// Error Boundary
// ============================================================================

/**
 * Chat runtime error with recovery info
 */
export class ChatRuntimeError extends Error {
  constructor(
    message: string,
    public readonly stage: 'entry' | 'process' | 'exit',
    public readonly recoverable: boolean,
    public readonly context?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ChatRuntimeError';
  }
}

/**
 * Assert chat runtime is healthy
 */
export function assertChatRuntimeHealthy(): void {
  const health = runtimeIntelligence.getRuntimeHealth();
  
  if (health.status === 'red') {
    throw new ChatRuntimeError(
      `Runtime health is red: ${health.reasons.join(', ')}`,
      'process',
      false,
      { health }
    );
  }
  
  // Check model health specifically
  const modelFallback = runtimeIntelligence.getModelHealthFallbackResult();
  if (!modelFallback.proceed) {
    throw new ChatRuntimeError(
      `Model health not ready: ${modelFallback.reason}`,
      'process',
      true,
      { modelFallback }
    );
  }
}

// ============================================================================
// Main Chat Runtime Function
// ============================================================================

/**
 * Execute full chat runtime flow: Entry → Process → Exit
 */
export async function executeChatRuntime(
  input: string,
  history: ChatMessage[],
  config: ChatRuntimeConfig = {}
): Promise<{
  success: boolean;
  exitState?: ChatExitState;
  error?: ChatRuntimeError;
}> {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  
  // === ENTRY ===
  const validation = validateChatEntry(input, cfg);
  if (!validation.valid) {
    return {
      success: false,
      error: new ChatRuntimeError(
        validation.errors.join(', '),
        'entry',
        true,
        { validation }
      ),
    };
  }
  
  // Entry guard
  const guardResult = await checkChatEntryGuard(input);
  if (!guardResult.pass) {
    return {
      success: false,
      error: new ChatRuntimeError(
        guardResult.reason ?? 'Entry guard failed',
        'entry',
        true,
        { guardResult }
      ),
    };
  }
  
  // === PROCESS ===
  let processResult: ChatProcessResult;
  
  try {
    assertChatRuntimeHealthy();
    processResult = await processChatMessage(validation.normalizedInput, history, cfg);
  } catch (error) {
    return {
      success: false,
      error: new ChatRuntimeError(
        error instanceof Error ? error.message : 'Process failed',
        'process',
        true,
        { error }
      ),
    };
  }
  
  // === EXIT ===
  const exitState = buildChatExitState(history, processResult, cfg);
  
  return {
    success: processResult.success,
    exitState,
  };
}
