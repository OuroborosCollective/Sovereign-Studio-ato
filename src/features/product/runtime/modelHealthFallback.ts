/**
 * Model Health Fallback Rules
 * 
 * Error boundary and fallback logic for model health runtime.
 * Provides safe degradation when health checks fail.
 * 
 * Features:
 * - Circuit breaker pattern for model health failures
 * - Fallback to cached/best-known model
 * - Graceful degradation when models are unavailable
 * - Telemetry for fallback events
 */

import type { ModelHealthCheckResult, ModelHealthReport } from './modelHealthRuntime';

/** Fallback strategy when primary model fails */
export type ModelHealthFallbackStrategy = 
  | 'use-cache'           // Use last known good model
  | 'use-any-enabled'      // Use any enabled model regardless of status
  | 'use-degraded'         // Accept degraded models
  | 'block'               // Block operations until healthy model available
  | 'no-op';              // Return null and let caller decide

/** Configuration for model health fallback */
export interface ModelHealthFallbackConfig {
  /** Strategy when best model is unavailable */
  primaryStrategy?: ModelHealthFallbackStrategy;
  /** Strategy when no healthy models available */
  degradedStrategy?: ModelHealthFallbackStrategy;
  /** Maximum consecutive failures before fallback activates */
  failureThreshold?: number;
  /** Maximum age (ms) of cached model before it's considered stale */
  cacheStaleMs?: number;
  /** Enable circuit breaker pattern */
  enableCircuitBreaker?: boolean;
  /** Number of failures to trip circuit breaker */
  circuitBreakerThreshold?: number;
  /** Time (ms) to keep circuit breaker open */
  circuitBreakerTimeoutMs?: number;
}

const DEFAULT_CONFIG: Required<ModelHealthFallbackConfig> = {
  primaryStrategy: 'use-any-enabled',
  degradedStrategy: 'use-degraded',
  failureThreshold: 3,
  cacheStaleMs: 300000, // 5 minutes
  enableCircuitBreaker: true,
  circuitBreakerThreshold: 5,
  circuitBreakerTimeoutMs: 60000, // 1 minute
};

/** Circuit breaker states */
export type ModelHealthCircuitState = 'closed' | 'open' | 'half-open';

/** Circuit breaker for model health */
export interface ModelHealthCircuitBreaker {
  state: ModelHealthCircuitState;
  failures: number;
  lastFailure: number | null;
  lastSuccess: number | null;
}

/** Fallback decision result */
export interface ModelHealthFallbackResult {
  /** Whether a fallback was used */
  usedFallback: boolean;
  /** The selected model */
  selectedModel: ModelHealthCheckResult | null;
  /** Fallback strategy used */
  strategy: ModelHealthFallbackStrategy | 'none';
  /** Reason for selection */
  reason: string;
  /** Whether operation should proceed */
  proceed: boolean;
  /** Circuit breaker state if applicable */
  circuitState?: ModelHealthCircuitState;
}

/** Runtime state for model health fallback */
export interface ModelHealthFallbackState {
  lastKnownGood: ModelHealthCheckResult | null;
  lastKnownGoodTimestamp: number | null;
  circuitBreaker: ModelHealthCircuitBreaker;
  consecutiveFailures: number;
  fallbackHistory: Array<{
    timestamp: number;
    strategy: ModelHealthFallbackStrategy;
    reason: string;
  }>;
}

/** Create initial fallback state */
export function createModelHealthFallbackState(): ModelHealthFallbackState {
  return {
    lastKnownGood: null,
    lastKnownGoodTimestamp: null,
    circuitBreaker: {
      state: 'closed',
      failures: 0,
      lastFailure: null,
      lastSuccess: null,
    },
    consecutiveFailures: 0,
    fallbackHistory: [],
  };
}

/**
 * Record a successful model usage
 */
export function recordModelSuccess(
  state: ModelHealthFallbackState,
  model: ModelHealthCheckResult
): ModelHealthFallbackState {
  return {
    ...state,
    lastKnownGood: model,
    lastKnownGoodTimestamp: Date.now(),
    consecutiveFailures: 0,
    circuitBreaker: {
      ...state.circuitBreaker,
      failures: 0,
      lastSuccess: Date.now(),
      state: state.circuitBreaker.state === 'half-open' ? 'closed' : state.circuitBreaker.state,
    },
  };
}

/**
 * Record a failed model usage
 */
export function recordModelFailure(
  state: ModelHealthFallbackState,
  config: Required<ModelHealthFallbackConfig>
): ModelHealthFallbackState {
  const now = Date.now();
  const newFailures = state.consecutiveFailures + 1;
  const circuitFailures = state.circuitBreaker.failures + 1;

  // Check if circuit breaker should trip
  let newCircuitState = state.circuitBreaker.state;
  if (config.enableCircuitBreaker && circuitFailures >= config.circuitBreakerThreshold) {
    newCircuitState = 'open';
  }

  return {
    ...state,
    consecutiveFailures: newFailures,
    circuitBreaker: {
      ...state.circuitBreaker,
      failures: circuitFailures,
      lastFailure: now,
      state: newCircuitState,
    },
  };
}

/**
 * Check if circuit breaker allows requests
 */
export function isCircuitBreakerOpen(
  state: ModelHealthFallbackState,
  config: Required<ModelHealthFallbackConfig>
): boolean {
  if (state.circuitBreaker.state === 'closed') return false;
  if (state.circuitBreaker.state === 'half-open') return false;

  // Check if timeout has passed to transition to half-open
  if (state.circuitBreaker.lastFailure) {
    const elapsed = Date.now() - state.circuitBreaker.lastFailure;
    if (elapsed >= config.circuitBreakerTimeoutMs) {
      return false; // Will transition to half-open
    }
  }

  return true;
}

/**
 * Try half-open state (probe request)
 */
export function tryHalfOpen(
  state: ModelHealthFallbackState
): ModelHealthFallbackState {
  if (state.circuitBreaker.state !== 'open') return state;

  return {
    ...state,
    circuitBreaker: {
      ...state.circuitBreaker,
      state: 'half-open',
    },
  };
}

/**
 * Check if cached model is still valid
 */
export function isCachedModelValid(
  state: ModelHealthFallbackState,
  config: Required<ModelHealthFallbackConfig>
): boolean {
  if (!state.lastKnownGood || !state.lastKnownGoodTimestamp) return false;
  
  const age = Date.now() - state.lastKnownGoodTimestamp;
  return age < config.cacheStaleMs;
}

/**
 * Select the best fallback model based on strategy
 */
export function selectFallbackModel(
  report: ModelHealthReport | null,
  state: ModelHealthFallbackState,
  config: Required<ModelHealthFallbackConfig>
): ModelHealthFallbackResult {
  // No report available - use cache if valid
  if (!report || report.results.length === 0) {
    if (isCachedModelValid(state, config) && config.primaryStrategy !== 'block') {
      return {
        usedFallback: true,
        selectedModel: state.lastKnownGood,
        strategy: 'use-cache',
        reason: `Using cached model (age: ${Date.now() - (state.lastKnownGoodTimestamp ?? 0)}ms)`,
        proceed: true,
        circuitState: state.circuitBreaker.state,
      };
    }

    return {
      usedFallback: true,
      selectedModel: null,
      strategy: config.primaryStrategy === 'block' ? 'block' : 'no-op',
      reason: 'No health report available and no valid cache',
      proceed: false,
      circuitState: state.circuitBreaker.state,
    };
  }

  // Find healthy models
  const healthyModels = report.results.filter(r => r.isEnabled && r.status === 'healthy');
  const degradedModels = report.results.filter(r => r.isEnabled && r.status === 'degraded');
  const allEnabledModels = report.results.filter(r => r.isEnabled);

  // Best case: healthy model available
  if (healthyModels.length > 0) {
    const best = healthyModels.sort((a, b) => (a.latencyMs ?? 0) - (b.latencyMs ?? 0))[0];
    return {
      usedFallback: false,
      selectedModel: best,
      strategy: 'none',
      reason: 'Healthy model available',
      proceed: true,
      circuitState: state.circuitBreaker.state,
    };
  }

  // Fallback strategies for degraded/no models
  const strategy = (healthyModels.length === 0 && degradedModels.length > 0 && config.primaryStrategy !== 'block')
    ? config.degradedStrategy
    : config.primaryStrategy;

  switch (strategy) {
    case 'block': {
      // Check cache
      if (isCachedModelValid(state, config)) {
        return {
          usedFallback: true,
          selectedModel: state.lastKnownGood,
          strategy: 'use-cache',
          reason: 'Blocked: no healthy models, using cached model',
          proceed: true,
          circuitState: state.circuitBreaker.state,
        };
      }

      return {
        usedFallback: true,
        selectedModel: null,
        strategy: 'block',
        reason: 'Blocked: no healthy models available',
        proceed: false,
        circuitState: state.circuitBreaker.state,
      };
    }

    case 'use-degraded': {
      if (degradedModels.length > 0) {
        const best = degradedModels.sort((a, b) => (a.latencyMs ?? 0) - (b.latencyMs ?? 0))[0];
        return {
          usedFallback: true,
          selectedModel: best,
          strategy: 'use-degraded',
          reason: `Using degraded model (${best.latencyMs}ms latency)`,
          proceed: true,
          circuitState: state.circuitBreaker.state,
        };
      }
      // Fall through to cache/no-op
    }

    case 'use-any-enabled': {
      if (allEnabledModels.length > 0) {
        const best = allEnabledModels.sort((a, b) => {
          // Unknown models last
          if (a.status === 'unknown' && b.status !== 'unknown') return 1;
          if (b.status === 'unknown' && a.status !== 'unknown') return -1;
          return (a.latencyMs ?? Infinity) - (b.latencyMs ?? Infinity);
        })[0];

        return {
          usedFallback: true,
          selectedModel: best,
          strategy: 'use-any-enabled',
          reason: `Using any enabled model (status: ${best.status})`,
          proceed: true,
          circuitState: state.circuitBreaker.state,
        };
      }
      // Fall through to cache/no-op
    }

    case 'use-cache': {
      if (isCachedModelValid(state, config)) {
        return {
          usedFallback: true,
          selectedModel: state.lastKnownGood,
          strategy: 'use-cache',
          reason: 'Using cached known-good model',
          proceed: true,
          circuitState: state.circuitBreaker.state,
        };
      }
      // Fall through to no-op
    }

    case 'no-op':
    default: {
      return {
        usedFallback: true,
        selectedModel: null,
        strategy: 'no-op',
        reason: 'No models available, returning null',
        proceed: false,
        circuitState: state.circuitBreaker.state,
      };
    }
  }
}

/**
 * Build a summary of fallback state for telemetry
 */
export function summarizeFallbackState(state: ModelHealthFallbackState): string {
  const parts: string[] = [];

  parts.push(`Circuit: ${state.circuitBreaker.state}`);
  parts.push(`Failures: ${state.consecutiveFailures}`);
  parts.push(`Cache age: ${state.lastKnownGoodTimestamp ? `${Date.now() - state.lastKnownGoodTimestamp}ms` : 'none'}`);

  if (state.fallbackHistory.length > 0) {
    const lastFallback = state.fallbackHistory[state.fallbackHistory.length - 1];
    parts.push(`Last fallback: ${lastFallback.strategy}`);
  }

  return parts.join(' · ');
}

/**
 * Assert model health is ready for operation
 * Throws if operation should not proceed
 */
export function assertModelHealthReadyForOperation(
  result: ModelHealthFallbackResult
): void {
  if (!result.proceed) {
    throw new Error(
      `Model health not ready: ${result.reason}. ` +
      `Strategy: ${result.strategy}, Circuit: ${result.circuitState}`
    );
  }
}
