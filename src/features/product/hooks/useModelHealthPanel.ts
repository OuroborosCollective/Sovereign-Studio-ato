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
  adapters: LlmAdapter[];
  checkIntervalMs?: number;
  timeoutMs?: number;
  degradedThresholdMs?: number;
  autoCheck?: boolean;
}

export interface UseModelHealthPanelReturn {
  models: ModelHealthStatus[];
  isChecking: boolean;
  lastCheck: number | null;
  onRefresh: () => void;
  healthyCount: number;
  degradedCount: number;
  unknownCount: number;
  hasAvailableModel: boolean;
  bestModel: ModelHealthStatus | null;
}

export function useModelHealthPanel(options: UseModelHealthPanelOptions): UseModelHealthPanelReturn {
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
  const healthyCount = useMemo(() => models.filter((model) => model.status === 'healthy').length, [models]);
  const degradedCount = useMemo(() => models.filter((model) => model.status === 'degraded').length, [models]);
  const unknownCount = useMemo(() => models.filter((model) => model.status === 'unknown').length, [models]);
  const bestModel = useMemo(() => getBestModel(), [getBestModel]);
  const hasAvailableModelValue = useMemo(() => hasAvailableModel(), [hasAvailableModel]);

  const onRefresh = useCallback(() => {
    void checkNow();
  }, [checkNow]);

  return {
    models,
    isChecking,
    lastCheck: lastGlobalCheck,
    onRefresh,
    healthyCount,
    degradedCount,
    unknownCount,
    hasAvailableModel: hasAvailableModelValue,
    bestModel,
  };
}
