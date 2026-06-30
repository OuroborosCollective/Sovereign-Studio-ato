/**
 * Model Health Runtime Tests
 */

import { describe, it, expect, vi } from 'vitest';
import {
  assertModelHealthReady,
  buildModelHealthStatusEntry,
  checkAllModelsHealth,
  checkModelHealth,
  createModelHealthRuntimeState,
  getBestModelFromReport,
  type ModelHealthCheckResult,
  type ModelHealthReport,
} from './modelHealthRuntime';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llm/llmAdapter';

const brain: LlmAdapterResult['brain'] = {
  perception: {
    domain: 'runtime-health',
    intent: 'probe adapter readiness',
    architecture: 'model health runtime',
    confidence: 1,
  },
  analysis: {
    severity: 'low',
    issues: [],
    rootCause: 'health probe mock response',
    systemicRisk: 'none',
  },
  plan: {
    strategy: 'return deterministic health response',
    phases: [],
    estimatedComplexity: 'trivial',
  },
  execution: {
    patches: [],
    integrationNotes: 'No code changes are produced by a health probe.',
    testStrategy: 'Use deterministic adapter mocks.',
  },
  learning: {
    patterns: ['health-probe'],
    rules: ['model health tests must satisfy the SovereignBrainResult contract'],
    architectureUpgrade: 'Keep health mocks aligned with the runtime brain contract.',
  },
};

const okResult: LlmAdapterResult = {
  providerId: 'local-safe',
  brain,
};

type TestAdapterInput = {
  id?: string;
  label?: string;
  enabled?: boolean;
  run?: LlmAdapter['run'];
};

function createTestAdapter(input: TestAdapterInput = {}): LlmAdapter {
  return {
    id: (input.id ?? 'local-safe') as LlmAdapter['id'],
    label: input.label ?? 'Local Safe',
    kind: 'local-safe',
    priority: 0,
    enabled: input.enabled ?? true,
    run: input.run ?? vi.fn().mockResolvedValue(okResult),
  };
}

function result(input: Partial<ModelHealthCheckResult> = {}): ModelHealthCheckResult {
  return {
    adapterId: 'model-a',
    adapterName: 'Model A',
    status: 'healthy',
    latencyMs: 12,
    lastCheck: 123,
    successCount: 1,
    errorCount: 0,
    isEnabled: true,
    ...input,
  };
}

function report(input: Partial<ModelHealthReport> = {}): ModelHealthReport {
  return {
    timestamp: Date.now(),
    totalModels: 0,
    healthyCount: 0,
    degradedCount: 0,
    unknownCount: 0,
    results: [],
    summary: 'No models',
    ...input,
  };
}

const fastConfig = {
  timeoutMs: 100,
  degradedThresholdMs: 50,
  testMission: 'OK',
};

describe('modelHealthRuntime', () => {
  it('creates initial state with null values', () => {
    const state = createModelHealthRuntimeState();

    expect(state.lastReport).toBeNull();
    expect(state.lastCheckTime).toBeNull();
    expect(state.isChecking).toBe(false);
    expect(state.consecutiveFailures).toBe(0);
  });

  it('returns healthy status when an enabled adapter responds quickly', async () => {
    const run = vi.fn().mockResolvedValue(okResult);
    const adapter = createTestAdapter({ id: 'fast-adapter', label: 'Fast Adapter', run });

    const health = await checkModelHealth(adapter, fastConfig);

    expect(health.status).toBe('healthy');
    expect(health.adapterId).toBe('fast-adapter');
    expect(health.adapterName).toBe('Fast Adapter');
    expect(health.successCount).toBe(1);
    expect(health.errorCount).toBe(0);
    expect(run).toHaveBeenCalledWith(expect.objectContaining({
      mission: 'OK',
      repoPaths: [],
      selectedFilePath: 'HEALTH_CHECK',
      allowExternalNoKey: false,
      allowOptInRoutes: false,
    } satisfies Partial<LlmAdapterContext>));
  });

  it('returns degraded status when latency exceeds the configured threshold', async () => {
    const adapter = createTestAdapter({
      id: 'slow-adapter',
      label: 'Slow Adapter',
      run: vi.fn().mockImplementation(async () => {
        await new Promise((resolve) => globalThis.setTimeout(resolve, 8));
        return okResult;
      }),
    });

    const health = await checkModelHealth(adapter, {
      timeoutMs: 100,
      degradedThresholdMs: 1,
      testMission: 'OK',
    });

    expect(health.status).toBe('degraded');
    expect(health.latencyMs).toBeGreaterThanOrEqual(1);
  });

  it('returns unknown status when an adapter fails', async () => {
    const adapter = createTestAdapter({
      id: 'failing-adapter',
      label: 'Failing Adapter',
      run: vi.fn().mockRejectedValue(new Error('Connection failed')),
    });

    const health = await checkModelHealth(adapter, fastConfig);

    expect(health.status).toBe('unknown');
    expect(health.errorCount).toBe(1);
    expect(health.successCount).toBe(0);
    expect(health.lastError).toBe('Connection failed');
  });

  it('does not call disabled adapters', async () => {
    const run = vi.fn().mockResolvedValue(okResult);
    const adapter = createTestAdapter({
      id: 'disabled-adapter',
      label: 'Disabled Adapter',
      enabled: false,
      run,
    });

    const health = await checkModelHealth(adapter, fastConfig);

    expect(health.status).toBe('unknown');
    expect(health.isEnabled).toBe(false);
    expect(run).not.toHaveBeenCalled();
  });

  it('reports a timeout as unknown when the adapter never resolves', async () => {
    const adapter = createTestAdapter({
      id: 'timeout-adapter',
      label: 'Timeout Adapter',
      run: vi.fn().mockImplementation(() => new Promise(() => undefined)),
    });

    const health = await checkModelHealth(adapter, {
      timeoutMs: 5,
      degradedThresholdMs: 1,
      testMission: 'Timeout',
    });

    expect(health.status).toBe('unknown');
    expect(health.lastError).toBe('Model health check timed out.');
  });

  it('checks all enabled models and returns aggregate report', async () => {
    const reportResult = await checkAllModelsHealth([
      createTestAdapter({ id: 'healthy-one', label: 'Healthy One' }),
      createTestAdapter({ id: 'disabled-one', label: 'Disabled One', enabled: false }),
    ], fastConfig);

    expect(reportResult.totalModels).toBe(2);
    expect(reportResult.results.length).toBe(2);
    expect(reportResult.healthyCount).toBe(1);
    expect(reportResult.unknownCount).toBe(1);
  });

  it('builds status entries with runtime field names', () => {
    const entry = buildModelHealthStatusEntry(result({
      adapterId: 'model-a',
      adapterName: 'Model A',
      status: 'healthy',
      latencyMs: 12,
      lastCheck: 123,
    }));

    expect(entry.id).toBe('model-a');
    expect(entry.name).toBe('Model A');
    expect(entry.status).toBe('healthy');
    expect(entry.lastCheck).toBe(123);
  });

  it('selects the lowest latency healthy model', () => {
    const best = getBestModelFromReport(report({
      results: [
        result({ adapterId: 'slow', adapterName: 'Slow', status: 'healthy', latencyMs: 50 }),
        result({ adapterId: 'fast', adapterName: 'Fast', status: 'healthy', latencyMs: 10 }),
      ],
    }));

    expect(best?.adapterId).toBe('fast');
  });

  it('returns null best model when no available model exists', () => {
    expect(getBestModelFromReport(report({
      results: [
        result({ adapterId: 'broken', adapterName: 'Broken', status: 'unknown', latencyMs: null, successCount: 0, errorCount: 1 }),
      ],
    }))).toBeNull();
  });

  it('does not throw readiness for healthy reports', () => {
    const healthReport = report({
      healthyCount: 1,
      results: [result({ adapterId: 'ok', adapterName: 'OK', status: 'healthy', latencyMs: 5 })],
    });

    expect(() => assertModelHealthReady(healthReport)).not.toThrow();
  });

  it('throws readiness error when no model is available', () => {
    expect(() => assertModelHealthReady(report({ healthyCount: 0, degradedCount: 0 }))).toThrow('No models available');
  });
});
