/**
 * Model Health Runtime
 *
 * Standalone runtime for LLM model health monitoring.
 * This module is intentionally UI-free: it probes real LLM adapters and returns
 * a report that UI components may display.
 */

import type { LlmAdapter, LlmAdapterContext } from '../llm/llmAdapter';

export type ModelHealthStatus = 'healthy' | 'degraded' | 'unknown';

export interface ModelHealthStatusEntry {
  id: string;
  name: string;
  status: ModelHealthStatus;
  latencyMs: number | null;
  lastCheck: number | null;
  errorCount: number;
  successCount: number;
  isEnabled: boolean;
  lastError?: string;
}

export interface ModelHealthRuntimeConfig {
  timeoutMs?: number;
  degradedThresholdMs?: number;
  testMission?: string;
}

const DEFAULT_CONFIG: Required<ModelHealthRuntimeConfig> = {
  timeoutMs: 5000,
  degradedThresholdMs: 2000,
  testMission: 'Respond with only: OK',
};

export interface ModelHealthCheckResult {
  adapterId: string;
  adapterName: string;
  status: ModelHealthStatus;
  latencyMs: number | null;
  lastCheck: number;
  errorCount: number;
  successCount: number;
  isEnabled: boolean;
  lastError?: string;
}

export interface ModelHealthReport {
  timestamp: number;
  totalModels: number;
  healthyCount: number;
  degradedCount: number;
  unknownCount: number;
  results: ModelHealthCheckResult[];
  summary: string;
}

export interface ModelHealthRuntimeState {
  lastReport: ModelHealthReport | null;
  lastCheckTime: number | null;
  isChecking: boolean;
  consecutiveFailures: number;
}

export function createModelHealthRuntimeState(): ModelHealthRuntimeState {
  return {
    lastReport: null,
    lastCheckTime: null,
    isChecking: false,
    consecutiveFailures: 0,
  };
}

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now();
}

function buildHealthTestContext(args: {
  adapterId: string;
  mission: string;
  signal?: AbortSignal;
}): LlmAdapterContext {
  return {
    mission: args.mission,
    repoPaths: [],
    selectedFilePath: 'HEALTH_CHECK',
    allowExternalNoKey: false,
    allowOptInRoutes: false,
    signal: args.signal,
    runtimeEvents: [`model-health:${args.adapterId}`],
  };
}

function abortError(parent?: AbortSignal): Error {
  return new Error(parent?.aborted ? 'Model health check aborted.' : 'Model health check timed out.');
}

function createTimeoutSignal(timeoutMs: number, parent?: AbortSignal): {
  signal: AbortSignal;
  cleanup: () => void;
} {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), Math.max(1, timeoutMs));
  const onParentAbort = () => controller.abort();

  if (parent) {
    if (parent.aborted) controller.abort();
    else parent.addEventListener('abort', onParentAbort, { once: true });
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      globalThis.clearTimeout(timeout);
      parent?.removeEventListener('abort', onParentAbort);
    },
  };
}

async function runWithAbort<T>(task: Promise<T>, signal: AbortSignal, parent?: AbortSignal): Promise<T> {
  if (signal.aborted) throw abortError(parent);

  return Promise.race([
    task,
    new Promise<never>((_, reject) => {
      signal.addEventListener('abort', () => reject(abortError(parent)), { once: true });
    }),
  ]);
}

function disabledResult(adapter: LlmAdapter): ModelHealthCheckResult {
  return {
    adapterId: adapter.id,
    adapterName: adapter.label,
    status: 'unknown',
    latencyMs: null,
    lastCheck: Date.now(),
    errorCount: 0,
    successCount: 0,
    isEnabled: false,
  };
}

export async function checkModelHealth(
  adapter: LlmAdapter,
  config: Required<ModelHealthRuntimeConfig>,
  signal?: AbortSignal,
): Promise<ModelHealthCheckResult> {
  if (!adapter.enabled) return disabledResult(adapter);

  const startTime = nowMs();
  const timeoutSignal = createTimeoutSignal(config.timeoutMs, signal);

  try {
    const context = buildHealthTestContext({
      adapterId: adapter.id,
      mission: config.testMission,
      signal: timeoutSignal.signal,
    });

    await runWithAbort(adapter.run(context), timeoutSignal.signal, signal);
    const latencyMs = Math.max(0, nowMs() - startTime);

    return {
      adapterId: adapter.id,
      adapterName: adapter.label,
      status: latencyMs < config.degradedThresholdMs ? 'healthy' : 'degraded',
      latencyMs: Math.round(latencyMs),
      lastCheck: Date.now(),
      errorCount: 0,
      successCount: 1,
      isEnabled: true,
    };
  } catch (error) {
    return {
      adapterId: adapter.id,
      adapterName: adapter.label,
      status: 'unknown',
      latencyMs: null,
      lastCheck: Date.now(),
      errorCount: 1,
      successCount: 0,
      isEnabled: adapter.enabled,
      lastError: error instanceof Error ? error.message : 'Health check failed',
    };
  } finally {
    timeoutSignal.cleanup();
  }
}

export async function checkAllModelsHealth(
  adapters: LlmAdapter[],
  config: ModelHealthRuntimeConfig = {},
  signal?: AbortSignal,
): Promise<ModelHealthReport> {
  const cfg = { ...DEFAULT_CONFIG, ...config } satisfies Required<ModelHealthRuntimeConfig>;
  const results: ModelHealthCheckResult[] = [];

  for (const adapter of adapters) {
    if (signal?.aborted) break;
    results.push(await checkModelHealth(adapter, cfg, signal));
  }

  const healthyCount = results.filter((result) => result.status === 'healthy').length;
  const degradedCount = results.filter((result) => result.status === 'degraded').length;
  const unknownCount = results.filter((result) => result.status === 'unknown').length;

  return {
    timestamp: Date.now(),
    totalModels: results.length,
    healthyCount,
    degradedCount,
    unknownCount,
    results,
    summary: [
      `${results.length} model(s) checked`,
      `${healthyCount} healthy`,
      `${degradedCount} degraded`,
      `${unknownCount} unknown`,
    ].join(' · '),
  };
}

export function buildModelHealthStatusEntry(result: ModelHealthCheckResult): ModelHealthStatusEntry {
  return {
    id: result.adapterId,
    name: result.adapterName,
    status: result.status,
    latencyMs: result.latencyMs,
    lastCheck: result.lastCheck,
    errorCount: result.errorCount,
    successCount: result.successCount,
    isEnabled: result.isEnabled,
    lastError: result.lastError,
  };
}

export function assertModelHealthReady(report: ModelHealthReport): void {
  if (report.healthyCount === 0 && report.degradedCount === 0) {
    throw new Error(`No models available. ${report.summary}`);
  }
}

export function getBestModelFromReport(report: ModelHealthReport): ModelHealthCheckResult | null {
  const available = report.results
    .filter((result) => result.isEnabled && result.status !== 'unknown')
    .sort((a, b) => {
      if (a.status !== b.status) return a.status === 'healthy' ? -1 : 1;
      if (a.latencyMs !== null && b.latencyMs !== null) return a.latencyMs - b.latencyMs;
      return b.successCount - a.successCount;
    });

  return available[0] ?? null;
}
