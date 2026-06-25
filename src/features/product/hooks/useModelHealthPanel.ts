/**
 * Model Health Panel Hook
 * 
 * Bridges useModelHealth hook with ModelHealthPanel component.
 * Provides ready-to-use props for the panel.
 */

import { useMemo, useCallback } from 'react';
import { useModelHealth, type ModelHealthStatus } from './useModelHealth';
import type { LlmAdapter } from '../llm/llmAdapter';

export interface UseModelHealthPanelOptions {
  /** List of LLM adapters to monitor */
  adapters: LlmAdapter[];
  /** Check interval in ms (default: 60000 = 1 minute) */
  checkIntervalMs?: number;
  /** Timeout per health check in ms (default: 5000) */
  timeoutMs?: number;
  /** Latency threshold for degraded status (default: 2000ms) */
  degradedThresholdMs?: number;
  /** Enable automatic health checks (default: true) */
  autoCheck?: boolean;
}

export interface UseModelHealthPanelReturn {
  /** Current health statuses for all models */
  models: ModelHealthStatus[];
  /** Whether health checks are currently running */
  isChecking: boolean;
  /** Timestamp of last health check */
  lastCheck: number | null;
  /** Callback to refresh health status */
  onRefresh: () => void;
  /** Count of healthy models */
  healthyCount: number;
  /** Count of degraded models */
  degradedCount: number;
  /** Count of unknown models */
  unknownCount: number;
  /** Whether any model is available */
  hasAvailableModel: boolean;
  /** Best available model */
  bestModel: ModelHealthStatus | null;
}

/**
 * Hook to provide ModelHealthPanel with data from useModelHealth
 */
export function useModelHealthPanel(
  options: UseModelHealthPanelOptions
): UseModelHealthPanelReturn {
  const {
    adapters,
    checkIntervalMs = 60000,
    timeoutMs = 5000,
    degradedThresholdMs = 2000,
    autoCheck = true,
  } = options;

  const {
    sortedModels,
    isChecking,
    lastGlobalCheck,
    checkNow,
    hasAvailableModel,
    getBestModel,
  } = useModelHealth(adapters, {
    checkIntervalMs,
    timeoutMs,
    degradedThresholdMs,
    autoCheck,
  });

  const models = useMemo(() => sortedModels, [sortedModels]);
  const healthyCount = useMemo(
    () => models.filter((m) => m.status === 'healthy').length,
    [models]
  );
  const degradedCount = useMemo(
    () => models.filter((m) => m.status === 'degraded').length,
    [models]
  );
  const unknownCount = useMemo(
    () => models.filter((m) => m.status === 'unknown').length,
    [models]
  );
  const bestModel = useMemo(() => getBestModel(), [getBestModel]);

  const onRefresh = useCallback(() => {
    checkNow();
  }, [checkNow]);

  return {
    models,
    isChecking,
    lastCheck: lastGlobalCheck,
    onRefresh,
    healthyCount,
    degradedCount,
    unknownCount,
    hasAvailableModel,
    bestModel,
  };
}
