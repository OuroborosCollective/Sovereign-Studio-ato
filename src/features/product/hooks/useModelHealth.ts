/**
 * Model Health Check Hook
 * 
 * Automatically checks which LLM models are available and responsive.
 * Integrates with predictive layer for intelligent routing.
 * 
 * Features:
 * - Periodic health checks
 * - Latency measurement
 * - Status tracking (healthy, degraded, down)
 * - Integration with LLM revolver
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { LlmAdapter } from '../llm/llmAdapter';

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
  /** Check interval in ms (default: 60000 = 1 minute) */
  checkIntervalMs?: number;
  /** Timeout per health check in ms (default: 5000) */
  timeoutMs?: number;
  /** Latency threshold for degraded status (default: 2000ms) */
  degradedThresholdMs?: number;
  /** Enable automatic health checks (default: true) */
  autoCheck?: boolean;
}

const DEFAULT_OPTIONS: Required<UseModelHealthOptions> = {
  checkIntervalMs: 60000,
  timeoutMs: 5000,
  degradedThresholdMs: 2000,
  autoCheck: true,
};

export interface UseModelHealthReturn {
  /** Current health status for all models */
  healthStatus: Map<string, ModelHealthStatus>;
  /** Models sorted by health (best first) */
  sortedModels: ModelHealthStatus[];
  /** Get best available model for routing */
  getBestModel: () => ModelHealthStatus | null;
  /** Force a health check now */
  checkNow: () => Promise<void>;
  /** Check if any model is available */
  hasAvailableModel: () => boolean;
  /** Get only healthy models */
  getHealthyModels: () => ModelHealthStatus[];
  /** Reset all health stats */
  reset: () => void;
  /** Last overall check timestamp */
  lastGlobalCheck: number | null;
  /** Whether health checks are running */
  isChecking: boolean;
}

/**
 * Hook for managing LLM model health status
 */
export function useModelHealth(
  adapters: LlmAdapter[],
  options: UseModelHealthOptions = {}
): UseModelHealthReturn {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  
  const [healthStatus, setHealthStatus] = useState<Map<string, ModelHealthStatus>>(new Map());
  const [lastGlobalCheck, setLastGlobalCheck] = useState<number | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  
  const checkIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Initialize health status from adapters
  useEffect(() => {
    const initialStatus = new Map<string, ModelHealthStatus>();
    
    for (const adapter of adapters) {
      initialStatus.set(adapter.id, {
        id: adapter.id,
        name: adapter.label,
        status: 'unknown',
        latencyMs: null,
        lastCheck: null,
        errorCount: 0,
        successCount: 0,
        isEnabled: adapter.enabled,
      });
    }
    
    setHealthStatus(initialStatus);
  }, [adapters]);

  // Perform a health check on a single model
  const checkSingleModel = useCallback(async (
    adapter: LlmAdapter,
    signal: AbortSignal
  ): Promise<ModelHealthStatus> => {
    const startTime = performance.now();
    
    try {
      // Make a simple test request
      const testContext = {
        mission: 'Health check',
        repoPaths: [],
        selectedFilePath: 'README.md',
        traceId: `health-${adapter.id}-${Date.now()}`,
        signal,
      };

      // Run with timeout
      const timeoutPromise = new Promise<'timeout'>((_, reject) => {
        setTimeout(() => reject('timeout'), opts.timeoutMs);
      });

      await Promise.race([
        adapter.run(testContext),
        timeoutPromise,
      ]);

      const latencyMs = performance.now() - startTime;
      
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

  // Check all models
  const checkAllModels = useCallback(async () => {
    if (isChecking) return;
    
    setIsChecking(true);
    
    // Cancel any previous check
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    
    const results = new Map<string, ModelHealthStatus>();
    
    for (const adapter of adapters) {
      if (!adapter.enabled) {
        results.set(adapter.id, {
          id: adapter.id,
          name: adapter.label,
          status: 'unknown',
          latencyMs: null,
          lastCheck: Date.now(),
          errorCount: 0,
          successCount: 0,
          isEnabled: false,
        });
        continue;
      }
      
      const result = await checkSingleModel(adapter, abortControllerRef.current.signal);
      results.set(adapter.id, result);
    }
    
    setHealthStatus(results);
    setLastGlobalCheck(Date.now());
    setIsChecking(false);
  }, [adapters, checkSingleModel, isChecking]);

  // Auto-start health checks
  useEffect(() => {
    if (!opts.autoCheck) return;
    
    // Initial check
    void checkAllModels();
    
    // Set up interval
    checkIntervalRef.current = setInterval(() => {
      void checkAllModels();
    }, opts.checkIntervalMs);
    
    return () => {
      if (checkIntervalRef.current) {
        clearInterval(checkIntervalRef.current);
      }
      abortControllerRef.current?.abort();
    };
  }, [opts.autoCheck, opts.checkIntervalMs, checkAllModels]);

  // Get models sorted by health
  const sortedModels = Array.from(healthStatus.values()).sort((a, b) => {
    // Disabled models last
    if (a.isEnabled !== b.isEnabled) return a.isEnabled ? -1 : 1;
    
    // Status priority: healthy > degraded > unknown
    const statusPriority = { healthy: 0, degraded: 1, unknown: 2 };
    const priorityDiff = statusPriority[a.status] - statusPriority[b.status];
    if (priorityDiff !== 0) return priorityDiff;
    
    // Then by latency (lower is better)
    if (a.latencyMs !== null && b.latencyMs !== null) {
      return a.latencyMs - b.latencyMs;
    }
    
    // Then by success rate
    const aRate = a.successCount / Math.max(a.successCount + a.errorCount, 1);
    const bRate = b.successCount / Math.max(b.successCount + b.errorCount, 1);
    return bRate - aRate;
  });

  // Get best available model
  const getBestModel = useCallback((): ModelHealthStatus | null => {
    return sortedModels.find(m => m.isEnabled && m.status !== 'unknown') || null;
  }, [sortedModels]);

  // Check if any model is available
  const hasAvailableModel = useCallback((): boolean => {
    return Array.from(healthStatus.values()).some(
      m => m.isEnabled && m.status !== 'unknown'
    );
  }, [healthStatus]);

  // Get only healthy models
  const getHealthyModels = useCallback((): ModelHealthStatus[] => {
    return sortedModels.filter(m => m.isEnabled && m.status === 'healthy');
  }, [sortedModels]);

  // Reset all stats
  const reset = useCallback(() => {
    setHealthStatus(prev => {
      const reset = new Map(prev);
      for (const [id, status] of reset) {
        reset.set(id, { ...status, errorCount: 0, successCount: 0 });
      }
      return reset;
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
