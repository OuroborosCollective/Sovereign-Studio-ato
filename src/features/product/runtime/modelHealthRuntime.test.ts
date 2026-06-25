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
      allowExternalNoKey: true,
      allowOptInRoutes: true,
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
      testMission: 'OK',
    });

    expect(result.status).toBe('unknown');
    expect(result.lastError).toContain('timed out');
  });

  it('checks all enabled adapters and builds a summary', async () => {
    const fast = createTestAdapter({ id: 'adapter-1', label: 'Adapter 1' });
    const disabled = createTestAdapter({ id: 'adapter-2', label: 'Adapter 2', enabled: false });

    const result = await checkAllModelsHealth([fast, disabled], fastConfig);

    expect(result.totalModels).toBe(2);
    expect(result.healthyCount).toBe(1);
    expect(result.degradedCount).toBe(0);
    expect(result.unknownCount).toBe(1);
    expect(result.summary).toContain('2 model(s) checked');
    expect(result.summary).toContain('1 healthy');
  });

  it('converts check result to status entry', () => {
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

  it('returns healthy models before degraded models', async () => {
    const healthy = createTestAdapter({ id: 'healthy', label: 'Healthy' });
    const degraded = createTestAdapter({
      id: 'degraded',
      label: 'Degraded',
      run: vi.fn().mockImplementation(async () => {
        await new Promise((resolve) => globalThis.setTimeout(resolve, 8));
        return okResult;
      }),
    });

    const result = await checkAllModelsHealth([degraded, healthy], {
      timeoutMs: 100,
      degradedThresholdMs: 1,
      testMission: 'OK',
    });
    const best = getBestModelFromReport(result);

    expect(best?.adapterId).toBe('healthy');
  });

  it('returns null when no models are available', () => {
    expect(getBestModelFromReport(report())).toBeNull();
  });

  it('accepts healthy or degraded reports and rejects all-unknown reports', () => {
    expect(() => assertModelHealthReady(report({ healthyCount: 1, summary: '1 healthy' }))).not.toThrow();
    expect(() => assertModelHealthReady(report({ degradedCount: 1, summary: '1 degraded' }))).not.toThrow();
    expect(() => assertModelHealthReady(report({ unknownCount: 1, summary: '1 unknown' }))).toThrow('No models available');
  });
});
