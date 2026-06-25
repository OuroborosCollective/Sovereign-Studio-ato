/**
 * Runtime Model Health Hook
 * 
 * Bridges RuntimeIntelligence model health with React components.
 * Provides integration with circuit breaker, fallback strategies, and telemetry.
 */

import { useEffect, useState, useCallback, useMemo } from 'react';
import { runtimeIntelligence } from '../../../runtime/RuntimeIntelligence';
import type { ModelHealthReport } from '../runtime/modelHealthRuntime';
import {
  type ModelHealthFallbackResult,
  type ModelHealthCircuitState,
} from '../runtime/modelHealthFallback';
import type { LlmAdapter } from '../llm/llmAdapter';

export interface UseRuntimeModelHealthOptions {
  /** List of LLM adapters to monitor */
  adapters: LlmAdapter[];
  /** Auto-start monitoring on mount (default: true) */
  autoStart?: boolean;
  /** Check interval in ms (default: 60000 = 1 minute) */
  checkIntervalMs?: number;
}

export interface UseRuntimeModelHealthReturn {
  /** Current health report from RuntimeIntelligence */
  report: ModelHealthReport | null;
  /** Fallback decision result */
  fallbackResult: ModelHealthFallbackResult;
  /** Whether monitoring is active */
  isMonitoring: boolean;
  /** Whether health check is running */
  isChecking: boolean;
  /** Timestamp of last check */
  lastCheck: number | null;
  /** Refresh health status now */
  refresh: () => Promise<void>;
  /** Start monitoring */
  start: () => void;
  /** Stop monitoring */
  stop: () => void;
  /** Record successful model usage */
  recordSuccess: (modelId: string) => void;
  /** Record failed model usage */
  recordFailure: (modelId: string) => void;
  /** Assert model health ready (throws if not) */
  assertReady: () => void;
  /** Current circuit breaker state */
  circuitState: ModelHealthCircuitState;
  /** Number of consecutive failures */
  consecutiveFailures: number;
}

const DEFAULT_CHECK_INTERVAL_MS = 60000;

/**
 * Hook to integrate RuntimeIntelligence model health with React
 */
export function useRuntimeModelHealth(
  options: UseRuntimeModelHealthOptions
): UseRuntimeModelHealthReturn {
  const { adapters, autoStart = true } = options;

  const [report, setReport] = useState<ModelHealthReport | null>(null);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [fallbackResult, setFallbackResult] = useState<ModelHealthFallbackResult>({
    usedFallback: false,
    selectedModel: null,
    strategy: 'none',
    reason: 'Not initialized',
    proceed: false,
    circuitState: 'closed',
  });

  // Initialize on mount
  useEffect(() => {
    // Set adapters
    runtimeIntelligence.setModelHealthAdapters(adapters);

    // Load initial report if available
    const initialReport = runtimeIntelligence.getModelHealthReport();
    if (initialReport) {
      setReport(initialReport);
      setFallbackResult(runtimeIntelligence.getModelHealthFallbackResult());
    }

    // Get monitoring state
    const fallbackState = runtimeIntelligence.getModelHealthFallbackState();
    setIsMonitoring(fallbackState.consecutiveFailures >= 0); // Simplified check

    return () => {
      // Cleanup: stop monitoring when unmounting
      runtimeIntelligence.stopModelHealthMonitoring();
      setIsMonitoring(false);
    };
  }, []); // Only on mount

  // Update adapters when they change
  useEffect(() => {
    runtimeIntelligence.setModelHealthAdapters(adapters);
  }, [adapters]);

  // Auto-start monitoring
  useEffect(() => {
    if (autoStart && adapters.length > 0) {
      runtimeIntelligence.startModelHealthMonitoring();
      setIsMonitoring(true);

      // Set up interval to poll report
      const interval = setInterval(() => {
        const currentReport = runtimeIntelligence.getModelHealthReport();
        if (currentReport) {
          setReport(currentReport);
          setFallbackResult(runtimeIntelligence.getModelHealthFallbackResult());
        }
      }, 5000); // Poll every 5 seconds

      return () => {
        clearInterval(interval);
        runtimeIntelligence.stopModelHealthMonitoring();
        setIsMonitoring(false);
      };
    }
  }, [autoStart, adapters.length]);

  const refresh = useCallback(async () => {
    const newReport = await runtimeIntelligence.checkModelHealth();
    if (newReport) {
      setReport(newReport);
      setFallbackResult(runtimeIntelligence.getModelHealthFallbackResult());
    }
  }, []);

  const start = useCallback(() => {
    runtimeIntelligence.startModelHealthMonitoring();
    setIsMonitoring(true);
  }, []);

  const stop = useCallback(() => {
    runtimeIntelligence.stopModelHealthMonitoring();
    setIsMonitoring(false);
  }, []);

  const recordSuccess = useCallback((modelId: string) => {
    runtimeIntelligence.recordModelSuccessForFallback(modelId);
    setFallbackResult(runtimeIntelligence.getModelHealthFallbackResult());
  }, []);

  const recordFailure = useCallback((modelId: string) => {
    runtimeIntelligence.recordModelFailureForFallback(modelId);
    setFallbackResult(runtimeIntelligence.getModelHealthFallbackResult());
  }, []);

  const assertReady = useCallback(() => {
    runtimeIntelligence.assertModelHealthReady();
  }, []);

  const circuitState = useMemo(() => {
    return fallbackResult.circuitState ?? 'closed';
  }, [fallbackResult.circuitState]);

  const consecutiveFailures = useMemo(() => {
    const state = runtimeIntelligence.getModelHealthFallbackState();
    return state.consecutiveFailures;
  }, [report]); // Re-compute when report changes

  const isChecking = useMemo(() => {
    const state = runtimeIntelligence.getModelHealthFallbackState();
    return state.consecutiveFailures >= 0; // Simplified
  }, []);

  return {
    report,
    fallbackResult,
    isMonitoring,
    isChecking,
    lastCheck: report?.timestamp ?? null,
    refresh,
    start,
    stop,
    recordSuccess,
    recordFailure,
    assertReady,
    circuitState,
    consecutiveFailures,
  };
}
