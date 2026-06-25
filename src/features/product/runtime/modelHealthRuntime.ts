/**
 * Model Health Runtime
 * 
 * Standalone runtime for LLM model health monitoring.
 * Can be used independently from React hooks for non-UI contexts.
 * 
 * Features:
 * - Health checks with configurable timeout
 * - Latency measurement
 * - Status classification (healthy, degraded, unknown)
 * - Health report generation
 */

import type { LlmAdapter, LlmAdapterContext } from '../llm/llmAdapter';

/** Health status levels */
export type ModelHealthStatus = 'healthy' | 'degraded' | 'unknown';

/** Individual model health status */
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

/** Configuration for health checks */
export interface ModelHealthRuntimeConfig {
  /** Timeout per health check in ms (default: 5000) */
  timeoutMs?: number;
  /** Latency threshold for degraded status in ms (default: 2000) */
  degradedThresholdMs?: number;
  /** Custom test mission (default: health check) */
  testMission?: string;
}

const DEFAULT_CONFIG: Required<ModelHealthRuntimeConfig> = {
  timeoutMs: 5000,
  degradedThresholdMs: 2000,
  testMission: 'Respond with only: OK',
};

/** Health check result for a single adapter */
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

/** Complete health report for all models */
export interface ModelHealthReport {
  timestamp: number;
  totalModels: number;
  healthyCount: number;
  degradedCount: number;
  unknownCount: number;
  results: ModelHealthCheckResult[];
  summary: string;
}

/** Runtime state for tracking health history */
export interface ModelHealthRuntimeState {
  lastReport: ModelHealthReport | null;
  lastCheckTime: number | null;
  isChecking: boolean;
  consecutiveFailures: number;
}

/**
 * Create initial runtime state
 */
export function createModelHealthRuntimeState(): ModelHealthRuntimeState {
  return {
    lastReport: null,
    lastCheckTime: null,
    isChecking: false,
    consecutiveFailures: 0,
  };
}

/**
 * Build a test context for health checking an adapter
 */
function buildHealthTestContext(adapterId: string, mission: string): LlmAdapterContext {
  return {
    mission,
    repoPaths: [],
    selectedFilePath: 'HEALTH_CHECK',
    allowExternalNoKey: true,
    allowOptInRoutes: true,
  };
}

/**
 * Check a single adapter's health
 */
export async function checkModelHealth(
  adapter: LlmAdapter,
  config: Required<ModelHealthRuntimeConfig>,
  signal?: AbortSignal
): Promise<ModelHealthCheckResult> {
  if (!adapter.enabled) {
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

  const startTime = performance.now();
  const testContext = buildHealthTestContext(adapter.id, config.testMission);

  // Create abort controller for timeout
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), config.timeoutMs);
  
  // Combine signals
  const abortController = new AbortController();
  const onAbort = () => abortController.abort();
  if (signal) signal.addEventListener('abort', onAbort);
  timeoutController.signal.addEventListener('abort', onAbort);

  try {
    const timeoutPromise = new Promise<never>((_, reject) => {
      timeoutController.signal.addEventListener('abort', () => reject(new Error('Timeout')));
    });

    await Promise.race([
      adapter.run({ ...testContext, signal: abortController.signal }),
      timeoutPromise,
    ]);

    const latencyMs = performance.now() - startTime;
    return {
      adapterId: adapter.id,
      adapterName: adapter.label,
      status: latencyMs < config.degradedThresholdMs ? 'healthy' : 'degraded',
      latencyMs: Math.round(latencyMs),
      lastCheck: Date.now(),
      errorCount: 0,
      successCount: 1,
      isEnabled: adapter.enabled,
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
    clearTimeout(timeoutId);
    if (signal) signal.removeEventListener('abort', onAbort);
  }
}

/**
 * Check all adapters and generate a health report
 */
export async function checkAllModelsHealth(
  adapters: LlmAdapter[],
  config: ModelHealthRuntimeConfig = {},
  signal?: AbortSignal
): Promise<ModelHealthReport> {
  const cfg = { ...DEFAULT_CONFIG, ...config } as Required<ModelHealthRuntimeConfig>;
  const results: ModelHealthCheckResult[] = [];

  for (const adapter of adapters) {
    if (!adapter.enabled) {
      results.push({
        adapterId: adapter.id,
        adapterName: adapter.label,
        status: 'unknown',
        latencyMs: null,
        lastCheck: Date.now(),
        errorCount: 0,
        successCount: 0,
        isEnabled: false,
      });
      continue;
    }

    if (signal?.aborted) break;
    
    const result = await checkModelHealth(adapter, cfg, signal);
    results.push(result);
  }

  const healthyCount = results.filter(r => r.status === 'healthy').length;
  const degradedCount = results.filter(r => r.status === 'degraded').length;
  const unknownCount = results.filter(r => r.status === 'unknown').length;

  const summary = [
    `${results.length} model(s) checked`,
    `${healthyCount} healthy`,
    `${degradedCount} degraded`,
    `${unknownCount} unknown`,
  ].join(' · ');

  return {
    timestamp: Date.now(),
    totalModels: results.length,
    healthyCount,
    degradedCount,
    unknownCount,
    results,
    summary,
  };
}

/**
 * Build a ModelHealthStatusEntry from a check result
 */
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

/**
 * Assert that at least one model is healthy and available
 */
export function assertModelHealthReady(report: ModelHealthReport): void {
  if (report.healthyCount === 0 && report.degradedCount === 0) {
    throw new Error(`No models available. ${report.summary}`);
  }
}

/**
 * Get the best available model from a report
 */
export function getBestModelFromReport(report: ModelHealthReport): ModelHealthCheckResult | null {
  const available = report.results
    .filter(r => r.isEnabled && r.status !== 'unknown')
    .sort((a, b) => {
      // Healthy before degraded
      if (a.status !== b.status) {
        return a.status === 'healthy' ? -1 : 1;
      }
      // Lower latency first
      if (a.latencyMs !== null && b.latencyMs !== null) {
        return a.latencyMs - b.latencyMs;
      }
      // More successes first
      return b.successCount - a.successCount;
    });

  return available[0] || null;
}
