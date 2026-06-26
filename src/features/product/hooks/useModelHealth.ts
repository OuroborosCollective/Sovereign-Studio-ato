/**
 * Model Health Check Hook
 *
 * Automatically checks which LLM models are available and responsive.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { LlmAdapter, LlmAdapterContext } from '../llm/llmAdapter';

export interface ModelHealthStatus {
  id: string;
  name: string;
  status: 'healthy' | 'degraded' | 'unknown';
  latencyMs: number | null;
  lastCheck: number | null;
  errorCount: number;
  successCount: number;
  isEnabled: boolean;
}

export interface UseModelHealthOptions {
  checkIntervalMs?: number;
  timeoutMs?: number;
  degradedThresholdMs?: number;
  autoCheck?: boolean;
}

const DEFAULT_OPTIONS: Required<UseModelHealthOptions> = {
  checkIntervalMs: 60000,
  timeoutMs: 5000,
  degradedThresholdMs: 2000,
  autoCheck: true,
};

export interface UseModelHealthReturn {
  healthStatus: Map<string, ModelHealthStatus>;
  sortedModels: ModelHealthStatus[];
  getBestModel: () => ModelHealthStatus | null;
  checkNow: () => Promise<void>;
  hasAvailableModel: () => boolean;
  getHealthyModels: () => ModelHealthStatus[];
  reset: () => void;
  lastGlobalCheck: number | null;
  isChecking: boolean;
}

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
}

function initialModelStatus(adapter: LlmAdapter): ModelHealthStatus {
  return {
    id: adapter.id,
    name: adapter.label,
    status: 'unknown',
    latencyMs: null,
    lastCheck: null,
    errorCount: 0,
    successCount: 0,
    isEnabled: adapter.enabled,
  };
}

export function useModelHealth(adapters: LlmAdapter[], options: UseModelHealthOptions = {}): UseModelHealthReturn {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const [healthStatus, setHealthStatus] = useState<Map<string, ModelHealthStatus>>(new Map());
  const [lastGlobalCheck, setLastGlobalCheck] = useState<number | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const checkIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const initialStatus = new Map<string, ModelHealthStatus>();
    for (const adapter of adapters) initialStatus.set(adapter.id, initialModelStatus(adapter));
    setHealthStatus(initialStatus);
  }, [adapters]);

  const checkSingleModel = useCallback(async (adapter: LlmAdapter, signal: AbortSignal): Promise<ModelHealthStatus> => {
    const startTime = nowMs();

    try {
      const testContext: LlmAdapterContext = {
        mission: 'Health check',
        repoPaths: [],
        selectedFilePath: 'README.md',
        signal,
        runtimeEvents: [`health:${adapter.id}`],
      };

      await Promise.race([
        adapter.run(testContext),
        new Promise<never>((_, reject) => {
          globalThis.setTimeout(() => reject(new Error('timeout')), Math.max(1, opts.timeoutMs));
        }),
      ]);

      const latencyMs = nowMs() - startTime;
      return {
        id: adapter.id,
        name: adapter.label,
        status: latencyMs < opts.degradedThresholdMs ? 'healthy' : 'degraded',
        latencyMs: Math.round(latencyMs),
        lastCheck: Date.now(),
        errorCount: 0,
        successCount: 1,
        isEnabled: adapter.enabled,
      };
    } catch {
      return {
        id: adapter.id,
        name: adapter.label,
        status: 'unknown',
        latencyMs: null,
        lastCheck: Date.now(),
        errorCount: 1,
        successCount: 0,
        isEnabled: adapter.enabled,
      };
    }
  }, [opts.timeoutMs, opts.degradedThresholdMs]);

  const checkAllModels = useCallback(async () => {
    if (isChecking) return;
    setIsChecking(true);
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    const results = new Map<string, ModelHealthStatus>();

    for (const adapter of adapters) {
      if (!adapter.enabled) {
        results.set(adapter.id, { ...initialModelStatus(adapter), lastCheck: Date.now() });
        continue;
      }

      const result = await checkSingleModel(adapter, abortControllerRef.current.signal);
      results.set(adapter.id, result);
    }

    setHealthStatus(results);
    setLastGlobalCheck(Date.now());
    setIsChecking(false);
  }, [adapters, checkSingleModel, isChecking]);

  useEffect(() => {
    if (!opts.autoCheck) return undefined;

    void checkAllModels();
    checkIntervalRef.current = setInterval(() => {
      void checkAllModels();
    }, opts.checkIntervalMs);

    return () => {
      if (checkIntervalRef.current) clearInterval(checkIntervalRef.current);
      abortControllerRef.current?.abort();
    };
  }, [opts.autoCheck, opts.checkIntervalMs, checkAllModels]);

  const sortedModels = Array.from(healthStatus.values()).sort((a, b) => {
    if (a.isEnabled !== b.isEnabled) return a.isEnabled ? -1 : 1;
    const statusPriority = { healthy: 0, degraded: 1, unknown: 2 };
    const priorityDiff = statusPriority[a.status] - statusPriority[b.status];
    if (priorityDiff !== 0) return priorityDiff;
    if (a.latencyMs !== null && b.latencyMs !== null) return a.latencyMs - b.latencyMs;
    const aRate = a.successCount / Math.max(a.successCount + a.errorCount, 1);
    const bRate = b.successCount / Math.max(b.successCount + b.errorCount, 1);
    return bRate - aRate;
  });

  const getBestModel = useCallback((): ModelHealthStatus | null => sortedModels.find((model) => model.isEnabled && model.status !== 'unknown') ?? null, [sortedModels]);
  const hasAvailableModel = useCallback((): boolean => Array.from(healthStatus.values()).some((model) => model.isEnabled && model.status !== 'unknown'), [healthStatus]);
  const getHealthyModels = useCallback((): ModelHealthStatus[] => sortedModels.filter((model) => model.isEnabled && model.status === 'healthy'), [sortedModels]);

  const reset = useCallback(() => {
    setHealthStatus((previous) => {
      const resetStatus = new Map(previous);
      for (const [id, status] of resetStatus) resetStatus.set(id, { ...status, errorCount: 0, successCount: 0 });
      return resetStatus;
    });
  }, []);

  return {
    healthStatus,
    sortedModels,
    getBestModel,
    checkNow: checkAllModels,
    hasAvailableModel,
    getHealthyModels,
    reset,
    lastGlobalCheck,
    isChecking,
  };
}

export default useModelHealth;
