/**
 * Model Health Runtime Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  checkModelHealth,
  checkAllModelsHealth,
  createModelHealthRuntimeState,
  buildModelHealthStatusEntry,
  assertModelHealthReady,
  getBestModelFromReport,
  type ModelHealthCheckResult,
} from './modelHealthRuntime';
import type { LlmAdapter, LlmAdapterResult, LlmAdapterContext } from '../llm/llmAdapter';

const createMockAdapter = (overrides: Partial<LlmAdapter> = {}): LlmAdapter => ({
  id: 'test-adapter' as LlmAdapter['id'],
  label: 'Test Adapter',
  kind: 'no-key',
  priority: 0,
  enabled: true,
  run: vi.fn(),
  ...overrides,
});

describe('modelHealthRuntime', () => {
  describe('createModelHealthRuntimeState', () => {
    it('should create initial state with null values', () => {
      const state = createModelHealthRuntimeState();
      
      expect(state.lastReport).toBeNull();
      expect(state.lastCheckTime).toBeNull();
      expect(state.isChecking).toBe(false);
      expect(state.consecutiveFailures).toBe(0);
    });
  });

  describe('checkModelHealth', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return healthy status when adapter responds quickly', async () => {
      const adapter = createMockAdapter({
        id: 'fast-adapter',
        label: 'Fast Adapter',
        run: vi.fn().mockResolvedValue({
          providerId: 'test',
          brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
        }),
      });

      const result = await checkModelHealth(adapter, {
        timeoutMs: 5000,
        degradedThresholdMs: 2000,
        testMission: 'OK',
      });

      expect(result.status).toBe('healthy');
      expect(result.adapterId).toBe('fast-adapter');
      expect(result.adapterName).toBe('Fast Adapter');
      expect(result.latencyMs).toBeLessThan(100);
      expect(result.successCount).toBe(1);
      expect(result.errorCount).toBe(0);
    });

    it('should return degraded status when adapter is slow', async () => {
      const adapter = createMockAdapter({
        id: 'slow-adapter',
        label: 'Slow Adapter',
        run: vi.fn().mockImplementation(async () => {
          await new Promise((resolve) => setTimeout(resolve, 2500));
          return {
            providerId: 'test',
            brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
          };
        }),
      });

      const result = await checkModelHealth(adapter, {
        timeoutMs: 5000,
        degradedThresholdMs: 2000,
        testMission: 'OK',
      });

      expect(result.status).toBe('degraded');
      expect(result.latencyMs).toBeGreaterThanOrEqual(2500);
    });

    it('should return unknown status when adapter fails', async () => {
      const adapter = createMockAdapter({
        id: 'failing-adapter',
        label: 'Failing Adapter',
        run: vi.fn().mockRejectedValue(new Error('Connection failed')),
      });

      const result = await checkModelHealth(adapter, {
        timeoutMs: 5000,
        degradedThresholdMs: 2000,
        testMission: 'OK',
      });

      expect(result.status).toBe('unknown');
      expect(result.errorCount).toBe(1);
      expect(result.successCount).toBe(0);
      expect(result.lastError).toBe('Connection failed');
    });

    it('should return unknown status for disabled adapters', async () => {
      const adapter = createMockAdapter({
        id: 'disabled-adapter',
        label: 'Disabled Adapter',
        enabled: false,
        run: vi.fn(),
      });

      const result = await checkModelHealth(adapter, {
        timeoutMs: 5000,
        degradedThresholdMs: 2000,
        testMission: 'OK',
      });

      expect(result.status).toBe('unknown');
      expect(result.isEnabled).toBe(false);
      expect(adapter.run).not.toHaveBeenCalled();
    });

    it('should respect timeout configuration', async () => {
      const adapter = createMockAdapter({
        id: 'timeout-adapter',
        label: 'Timeout Adapter',
        run: vi.fn().mockImplementation(async () => {
          await new Promise((resolve) => setTimeout(resolve, 10000));
          return {
            providerId: 'test',
            brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
          };
        }),
      });

      const result = await checkModelHealth(adapter, {
        timeoutMs: 100,
        degradedThresholdMs: 2000,
        testMission: 'OK',
      });

      expect(result.status).toBe('unknown');
      expect(result.lastError).toContain('Health check failed');
    });
  });

  describe('checkAllModelsHealth', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should check all enabled adapters', async () => {
      const adapter1 = createMockAdapter({
        id: 'adapter-1',
        label: 'Adapter 1',
        run: vi.fn().mockResolvedValue({
          providerId: 'test',
          brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
        }),
      });
      const adapter2 = createMockAdapter({
        id: 'adapter-2',
        label: 'Adapter 2',
        run: vi.fn().mockResolvedValue({
          providerId: 'test',
          brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
        }),
      });

      const report = await checkAllModelsHealth([adapter1, adapter2]);

      expect(report.totalModels).toBe(2);
      expect(report.results).toHaveLength(2);
      expect(report.healthyCount).toBe(2);
      expect(report.degradedCount).toBe(0);
      expect(report.unknownCount).toBe(0);
    });

    it('should handle mixed healthy and degraded adapters', async () => {
      const fastAdapter = createMockAdapter({
        id: 'fast',
        label: 'Fast',
        run: vi.fn().mockResolvedValue({
          providerId: 'test',
          brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
        }),
      });
      const slowAdapter = createMockAdapter({
        id: 'slow',
        label: 'Slow',
        run: vi.fn().mockImplementation(async () => {
          await new Promise((resolve) => setTimeout(resolve, 3000));
          return {
            providerId: 'test',
            brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
          };
        }),
      });
      const failingAdapter = createMockAdapter({
        id: 'failing',
        label: 'Failing',
        run: vi.fn().mockRejectedValue(new Error('Error')),
      });

      const report = await checkAllModelsHealth([fastAdapter, slowAdapter, failingAdapter]);

      expect(report.totalModels).toBe(3);
      expect(report.healthyCount).toBe(1);
      expect(report.degradedCount).toBe(1);
      expect(report.unknownCount).toBe(1);
    });

    it('should generate a summary string', async () => {
      const adapter = createMockAdapter({
        id: 'test',
        label: 'Test',
        run: vi.fn().mockResolvedValue({
          providerId: 'test',
          brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
        }),
      });

      const report = await checkAllModelsHealth([adapter]);

      expect(report.summary).toContain('1 model(s) checked');
      expect(report.summary).toContain('1 healthy');
    });

    it('should return report with timestamp', async () => {
      const adapter = createMockAdapter({
        id: 'test',
        label: 'Test',
        run: vi.fn().mockResolvedValue({
          providerId: 'test',
          brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
        }),
      });

      const beforeTime = Date.now();
      const report = await checkAllModelsHealth([adapter]);
      const afterTime = Date.now();

      expect(report.timestamp).toBeGreaterThanOrEqual(beforeTime);
      expect(report.timestamp).toBeLessThanOrEqual(afterTime);
    });
  });

  describe('buildModelHealthStatusEntry', () => {
    it('should convert check result to status entry', () => {
      const checkResult: ModelHealthCheckResult = {
        adapterId: 'test-id',
        adapterName: 'Test Name',
        status: 'healthy',
        latencyMs: 150,
        lastCheck: 1234567890,
        errorCount: 0,
        successCount: 5,
        isEnabled: true,
      };

      const entry = buildModelHealthStatusEntry(checkResult);

      expect(entry.id).toBe('test-id');
      expect(entry.name).toBe('Test Name');
      expect(entry.status).toBe('healthy');
      expect(entry.latencyMs).toBe(150);
      expect(entry.lastCheck).toBe(1234567890);
      expect(entry.errorCount).toBe(0);
      expect(entry.successCount).toBe(5);
      expect(entry.isEnabled).toBe(true);
    });
  });

  describe('getBestModelFromReport', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return healthy model over degraded', async () => {
      const healthyAdapter = createMockAdapter({
        id: 'healthy',
        label: 'Healthy',
        run: vi.fn().mockResolvedValue({
          providerId: 'test',
          brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
        }),
      });
      const degradedAdapter = createMockAdapter({
        id: 'degraded',
        label: 'Degraded',
        run: vi.fn().mockImplementation(async () => {
          await new Promise((resolve) => setTimeout(resolve, 3000));
          return {
            providerId: 'test',
            brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
          };
        }),
      });

      const report = await checkAllModelsHealth([degradedAdapter, healthyAdapter]);
      const best = getBestModelFromReport(report);

      expect(best?.adapterId).toBe('healthy');
    });

    it('should return model with lower latency first', async () => {
      const slowAdapter = createMockAdapter({
        id: 'slow',
        label: 'Slow',
        run: vi.fn().mockImplementation(async () => {
          await new Promise((resolve) => setTimeout(resolve, 100));
          return {
            providerId: 'test',
            brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
          };
        }),
      });
      const fastAdapter = createMockAdapter({
        id: 'fast',
        label: 'Fast',
        run: vi.fn().mockResolvedValue({
          providerId: 'test',
          brain: { perception: '', analysis: '', plan: '', execution: { patches: [] }, learning: null },
        }),
      });

      const report = await checkAllModelsHealth([slowAdapter, fastAdapter]);
      const best = getBestModelFromReport(report);

      expect(best?.adapterId).toBe('fast');
    });

    it('should return null when no models available', () => {
      const report = {
        timestamp: Date.now(),
        totalModels: 0,
        healthyCount: 0,
        degradedCount: 0,
        unknownCount: 0,
        results: [],
        summary: 'No models',
      };

      const best = getBestModelFromReport(report);

      expect(best).toBeNull();
    });
  });

  describe('assertModelHealthReady', () => {
    it('should not throw when healthy models available', () => {
      const report = {
        timestamp: Date.now(),
        totalModels: 1,
        healthyCount: 1,
        degradedCount: 0,
        unknownCount: 0,
        results: [{
          adapterId: 'test',
          adapterName: 'Test',
          status: 'healthy' as const,
          latencyMs: 100,
          lastCheck: Date.now(),
          errorCount: 0,
          successCount: 1,
          isEnabled: true,
        }],
        summary: '1 healthy',
      };

      expect(() => assertModelHealthReady(report)).not.toThrow();
    });

    it('should not throw when degraded models available', () => {
      const report = {
        timestamp: Date.now(),
        totalModels: 1,
        healthyCount: 0,
        degradedCount: 1,
        unknownCount: 0,
        results: [{
          adapterId: 'test',
          adapterName: 'Test',
          status: 'degraded' as const,
          latencyMs: 3000,
          lastCheck: Date.now(),
          errorCount: 0,
          successCount: 1,
          isEnabled: true,
        }],
        summary: '1 degraded',
      };

      expect(() => assertModelHealthReady(report)).not.toThrow();
    });

    it('should throw when no models available', () => {
      const report = {
        timestamp: Date.now(),
        totalModels: 1,
        healthyCount: 0,
        degradedCount: 0,
        unknownCount: 1,
        results: [{
          adapterId: 'test',
          adapterName: 'Test',
          status: 'unknown' as const,
          latencyMs: null,
          lastCheck: Date.now(),
          errorCount: 1,
          successCount: 0,
          isEnabled: true,
        }],
        summary: '1 unknown',
      };

      expect(() => assertModelHealthReady(report)).toThrow('No models available');
    });
  });
});
