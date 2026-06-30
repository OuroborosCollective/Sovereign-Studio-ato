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

    const result = await checkModelHealth(adapter, fastConfig);

    expect(result.status).toBe('healthy');
    expect(result.adapterId).toBe('fast-adapter');
    expect(result.adapterName).toBe('Fast Adapter');
    expect(result.successCount).toBe(1);
    expect(result.errorCount).toBe(0);
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

    const result = await checkModelHealth(adapter, {
      timeoutMs: 100,
      degradedThresholdMs: 1,
      testMission: 'OK',
    });

    expect(result.status).toBe('degraded');
    expect(result.latencyMs).toBeGreaterThanOrEqual(1);
  });

  it('returns unknown status when an adapter fails', async () => {
    const adapter = createTestAdapter({
      id: 'failing-adapter',
      label: 'Failing Adapter',
      run: vi.fn().mockRejectedValue(new Error('Connection failed')),
    });

    const result = await checkModelHealth(adapter, fastConfig);

    expect(result.status).toBe('unknown');
    expect(result.errorCount).toBe(1);
    expect(result.successCount).toBe(0);
    expect(result.lastError).toBe('Connection failed');
  });

  it('does not call disabled adapters', async () => {
    const run = vi.fn().mockResolvedValue(okResult);
    const adapter = createTestAdapter({
      id: 'disabled-adapter',
      label: 'Disabled Adapter',
      enabled: false,
      run,
    });

    const result = await checkModelHealth(adapter, fastConfig);

    expect(result.status).toBe('unknown');
    expect(result.isEnabled).toBe(false);
    expect(run).not.toHaveBeenCalled();
  });

  it('reports a timeout as unknown when the adapter never resolves', async () => {
    const adapter = createTestAdapter({
      id: 'timeout-adapter',
      label: 'Timeout Adapter',
      run: vi.fn().mockImplementation(() => new Promise(() => undefined)),
    });

    const result = await checkModelHealth(adapter, {
      timeoutMs: 5,
      degradedThresholdMs: 1,
      testMission: 'Timeout',
    });

    expect(result.status).toBe('unknown');
    expect(result.lastError).toBe('timeout');
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

  it('builds status entries with deterministic labels', () => {
    const entry = buildModelHealthStatusEntry({
      adapterId: 'model-a',
      adapterName: 'Model A',
      status: 'healthy',
      latencyMs: 12,
      lastChecked: 123,
      successCount: 1,
      errorCount: 0,
      isEnabled: true,
    });

    expect(entry.id).toBe('model-a');
    expect(entry.label).toBe('Model A');
    expect(entry.kind).toBe('healthy');
  });

  it('selects the lowest latency healthy model', () => {
    const best = getBestModelFromReport(report({
      results: [
        { adapterId: 'slow', adapterName: 'Slow', status: 'healthy', latencyMs: 50, lastChecked: 1, successCount: 1, errorCount: 0, isEnabled: true },
        { adapterId: 'fast', adapterName: 'Fast', status: 'healthy', latencyMs: 10, lastChecked: 1, successCount: 1, errorCount: 0, isEnabled: true },
      ],
    }));

    expect(best?.adapterId).toBe('fast');
  });

  it('returns null best model when no healthy model exists', () => {
    expect(getBestModelFromReport(report({
      results: [
        { adapterId: 'broken', adapterName: 'Broken', status: 'unknown', latencyMs: null, lastChecked: 1, successCount: 0, errorCount: 1, isEnabled: true },
      ],
    }))).toBeNull();
  });

  it('asserts readiness for healthy reports', () => {
    const healthReport = report({ healthyCount: 1, results: [
      { adapterId: 'ok', adapterName: 'OK', status: 'healthy', latencyMs: 5, lastChecked: 1, successCount: 1, errorCount: 0, isEnabled: true },
    ] });

    expect(assertModelHealthReady(healthReport).ok).toBe(true);
  });

  it('blocks readiness when no healthy model exists', () => {
    const result = assertModelHealthReady(report({ healthyCount: 0 }));

    expect(result.ok).toBe(false);
    expect(result.reason).toContain('No healthy model');
  });
});
