/**
 * Model Health Fallback Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  createModelHealthFallbackState,
  recordModelSuccess,
  recordModelFailure,
  isCachedModelValid,
  isCircuitBreakerOpen,
  selectFallbackModel,
  assertModelHealthReadyForOperation,
  summarizeFallbackState,
  type ModelHealthFallbackConfig,
  type ModelHealthFallbackResult,
} from './modelHealthFallback';
import type { ModelHealthReport } from './modelHealthRuntime';

const createMockReport = (overrides: Partial<ModelHealthReport> = {}): ModelHealthReport => ({
  timestamp: Date.now(),
  totalModels: 1,
  healthyCount: 1,
  degradedCount: 0,
  unknownCount: 0,
  results: [{
    adapterId: 'test-adapter',
    adapterName: 'Test Adapter',
    status: 'healthy',
    latencyMs: 100,
    lastCheck: Date.now(),
    errorCount: 0,
    successCount: 1,
    isEnabled: true,
  }],
  summary: '1 healthy',
  ...overrides,
});

const defaultConfig: Required<ModelHealthFallbackConfig> = {
  primaryStrategy: 'use-any-enabled',
  degradedStrategy: 'use-degraded',
  failureThreshold: 3,
  cacheStaleMs: 300000,
  enableCircuitBreaker: true,
  circuitBreakerThreshold: 5,
  circuitBreakerTimeoutMs: 60000,
};

describe('modelHealthFallback', () => {
  describe('createModelHealthFallbackState', () => {
    it('should create initial state', () => {
      const state = createModelHealthFallbackState();
      
      expect(state.lastKnownGood).toBeNull();
      expect(state.lastKnownGoodTimestamp).toBeNull();
      expect(state.consecutiveFailures).toBe(0);
      expect(state.fallbackHistory).toEqual([]);
      expect(state.circuitBreaker.state).toBe('closed');
      expect(state.circuitBreaker.failures).toBe(0);
    });
  });

  describe('recordModelSuccess', () => {
    it('should update last known good model', () => {
      const state = createModelHealthFallbackState();
      const model = {
        adapterId: 'test',
        adapterName: 'Test',
        status: 'healthy' as const,
        latencyMs: 100,
        lastCheck: Date.now(),
        errorCount: 0,
        successCount: 1,
        isEnabled: true,
      };

      const newState = recordModelSuccess(state, model);

      expect(newState.lastKnownGood).toEqual(model);
      expect(newState.lastKnownGoodTimestamp).not.toBeNull();
      expect(newState.consecutiveFailures).toBe(0);
      expect(newState.circuitBreaker.failures).toBe(0);
      expect(newState.circuitBreaker.state).toBe('closed');
    });

    it('should reset circuit breaker on success', () => {
      const state = {
        ...createModelHealthFallbackState(),
        circuitBreaker: {
          state: 'half-open' as const,
          failures: 3,
          lastFailure: Date.now() - 1000,
          lastSuccess: null,
        },
      };
      const model = {
        adapterId: 'test',
        adapterName: 'Test',
        status: 'healthy' as const,
        latencyMs: 100,
        lastCheck: Date.now(),
        errorCount: 0,
        successCount: 1,
        isEnabled: true,
      };

      const newState = recordModelSuccess(state, model);

      expect(newState.circuitBreaker.state).toBe('closed');
      expect(newState.circuitBreaker.failures).toBe(0);
    });
  });

  describe('recordModelFailure', () => {
    it('should increment consecutive failures', () => {
      const state = createModelHealthFallbackState();
      const config = { ...defaultConfig, enableCircuitBreaker: false };

      const newState = recordModelFailure(state, config);

      expect(newState.consecutiveFailures).toBe(1);
    });

    it('should trip circuit breaker after threshold', () => {
      const state = createModelHealthFallbackState();
      const config = { ...defaultConfig, circuitBreakerThreshold: 3 };

      let currentState = state;
      for (let i = 0; i < 3; i++) {
        currentState = recordModelFailure(currentState, config);
      }

      expect(currentState.circuitBreaker.state).toBe('open');
    });
  });

  describe('isCachedModelValid', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(Date.now());
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return false when no cache exists', () => {
      const state = createModelHealthFallbackState();
      const config = { ...defaultConfig };

      expect(isCachedModelValid(state, config)).toBe(false);
    });

    it('should return true when cache is fresh', () => {
      const state = {
        ...createModelHealthFallbackState(),
        lastKnownGood: {
          adapterId: 'test',
          adapterName: 'Test',
          status: 'healthy' as const,
          latencyMs: 100,
          lastCheck: Date.now(),
          errorCount: 0,
          successCount: 1,
          isEnabled: true,
        },
        lastKnownGoodTimestamp: Date.now() - 60000,
      };
      const config = { ...defaultConfig, cacheStaleMs: 300000 };

      expect(isCachedModelValid(state, config)).toBe(true);
    });

    it('should return false when cache is stale', () => {
      const state = {
        ...createModelHealthFallbackState(),
        lastKnownGood: {
          adapterId: 'test',
          adapterName: 'Test',
          status: 'healthy' as const,
          latencyMs: 100,
          lastCheck: Date.now() - 600000,
          errorCount: 0,
          successCount: 1,
          isEnabled: true,
        },
        lastKnownGoodTimestamp: Date.now() - 600000,
      };
      const config = { ...defaultConfig, cacheStaleMs: 300000 };

      expect(isCachedModelValid(state, config)).toBe(false);
    });
  });

  describe('isCircuitBreakerOpen', () => {
    it('should return false when circuit is closed', () => {
      const state = {
        ...createModelHealthFallbackState(),
        circuitBreaker: { state: 'closed' as const, failures: 0, lastFailure: null, lastSuccess: null },
      };

      expect(isCircuitBreakerOpen(state, defaultConfig)).toBe(false);
    });

    it('should return false when circuit is half-open', () => {
      const state = {
        ...createModelHealthFallbackState(),
        circuitBreaker: { state: 'half-open' as const, failures: 0, lastFailure: null, lastSuccess: null },
      };

      expect(isCircuitBreakerOpen(state, defaultConfig)).toBe(false);
    });

    it('should return true when circuit is open within timeout', () => {
      const state = {
        ...createModelHealthFallbackState(),
        circuitBreaker: {
          state: 'open' as const,
          failures: 5,
          lastFailure: Date.now() - 30000,
          lastSuccess: null,
        },
      };

      expect(isCircuitBreakerOpen(state, defaultConfig)).toBe(true);
    });

    it('should return false when circuit is open but timeout expired', () => {
      const state = {
        ...createModelHealthFallbackState(),
        circuitBreaker: {
          state: 'open' as const,
          failures: 5,
          lastFailure: Date.now() - 90000,
          lastSuccess: null,
        },
      };

      expect(isCircuitBreakerOpen(state, defaultConfig)).toBe(false);
    });
  });

  describe('selectFallbackModel', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(Date.now());
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return healthy model when available', () => {
      const report = createMockReport({
        results: [{
          adapterId: 'healthy',
          adapterName: 'Healthy',
          status: 'healthy' as const,
          latencyMs: 100,
          lastCheck: Date.now(),
          errorCount: 0,
          successCount: 1,
          isEnabled: true,
        }],
      });
      const state = createModelHealthFallbackState();

      const result = selectFallbackModel(report, state, defaultConfig);

      expect(result.proceed).toBe(true);
      expect(result.selectedModel?.adapterId).toBe('healthy');
      expect(result.strategy).toBe('none');
      expect(result.usedFallback).toBe(false);
    });

    it('should fallback to degraded when no healthy available', () => {
      const report = createMockReport({
        healthyCount: 0,
        degradedCount: 1,
        results: [{
          adapterId: 'degraded',
          adapterName: 'Degraded',
          status: 'degraded' as const,
          latencyMs: 3000,
          lastCheck: Date.now(),
          errorCount: 0,
          successCount: 1,
          isEnabled: true,
        }],
      });
      const state = createModelHealthFallbackState();

      const result = selectFallbackModel(report, state, defaultConfig);

      expect(result.proceed).toBe(true);
      expect(result.selectedModel?.adapterId).toBe('degraded');
      expect(result.strategy).toBe('use-degraded');
      expect(result.usedFallback).toBe(true);
    });

    it('should use cache when no models available', () => {
      const state = {
        ...createModelHealthFallbackState(),
        lastKnownGood: {
          adapterId: 'cached',
          adapterName: 'Cached',
          status: 'healthy' as const,
          latencyMs: 100,
          lastCheck: Date.now(),
          errorCount: 0,
          successCount: 5,
          isEnabled: true,
        },
        lastKnownGoodTimestamp: Date.now() - 60000,
      };

      const result = selectFallbackModel(null, state, defaultConfig);

      expect(result.proceed).toBe(true);
      expect(result.selectedModel?.adapterId).toBe('cached');
      expect(result.strategy).toBe('use-cache');
      expect(result.usedFallback).toBe(true);
    });

    it('should block when strategy is block and no healthy model', () => {
      const report = createMockReport({
        healthyCount: 0,
        degradedCount: 1,
        results: [{
          adapterId: 'degraded',
          adapterName: 'Degraded',
          status: 'degraded' as const,
          latencyMs: 3000,
          lastCheck: Date.now(),
          errorCount: 0,
          successCount: 1,
          isEnabled: true,
        }],
      });
      const state = createModelHealthFallbackState();
      const blockConfig = { ...defaultConfig, primaryStrategy: 'block' as const };

      const result = selectFallbackModel(report, state, blockConfig);

      expect(result.proceed).toBe(false);
      expect(result.selectedModel).toBeNull();
      expect(result.strategy).toBe('block');
    });
  });

  describe('assertModelHealthReadyForOperation', () => {
    it('should not throw when proceed is true', () => {
      const result: ModelHealthFallbackResult = {
        usedFallback: false,
        selectedModel: { adapterId: 'test', adapterName: 'Test', status: 'healthy', latencyMs: 100, lastCheck: 0, errorCount: 0, successCount: 1, isEnabled: true },
        strategy: 'none',
        reason: 'Healthy model available',
        proceed: true,
      };

      expect(() => assertModelHealthReadyForOperation(result)).not.toThrow();
    });

    it('should throw when proceed is false', () => {
      const result: ModelHealthFallbackResult = {
        usedFallback: true,
        selectedModel: null,
        strategy: 'block',
        reason: 'No models available',
        proceed: false,
      };

      expect(() => assertModelHealthReadyForOperation(result)).toThrow('Model health not ready');
    });
  });

  describe('summarizeFallbackState', () => {
    it('should return summary string', () => {
      const state = {
        ...createModelHealthFallbackState(),
        lastKnownGoodTimestamp: Date.now() - 60000,
        consecutiveFailures: 2,
        fallbackHistory: [{ timestamp: Date.now() - 5000, strategy: 'use-cache' as const, reason: 'Cache hit' }],
      };

      const summary = summarizeFallbackState(state);

      expect(summary).toContain('Circuit: closed');
      expect(summary).toContain('Failures: 2');
      expect(summary).toContain('Last fallback: use-cache');
    });
  });
});
