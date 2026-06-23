/**
 * Predictive Layer React Hooks
 *
 * Hooks expose predictive state as advisory runtime signals only. UI consumers
 * must not treat confidence as proof of success.
 *
 * @module predictive/predictiveHooks
 */

import React, { useState, useCallback, useEffect, useMemo, useContext } from 'react';
import { PredictiveGuard, type PredictiveGuardConfig, type SafetyContext, type SafetyCheckResult, type DecisionOutcome } from './predictiveGuard';
import { PredictiveLayer } from './predictiveLayer';
import type { PredictiveLayerSnapshot, PredictiveMetrics, PredictiveLayerConfig, Signal } from './types';

export interface PredictiveLayerContextValue {
  layer: PredictiveLayer | null;
  isActive: boolean;
  snapshot: PredictiveLayerSnapshot | null;
  metrics: PredictiveMetrics | null;
  confidence: number;
  errorRate: number;
  isLowConfidence: boolean;
  isHighErrorRate: boolean;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  emitSignal: (signal: Signal) => void;
}

const PredictiveLayerContext = React.createContext<PredictiveLayerContextValue | null>(null);

export interface UsePredictiveLayerOptions {
  config?: PredictiveLayerConfig;
  autoStart?: boolean;
  confidenceThreshold?: number;
  errorRateThreshold?: number;
}

function createNoLayerValue(): PredictiveLayerContextValue {
  return {
    layer: null,
    isActive: false,
    snapshot: null,
    metrics: null,
    confidence: 0,
    errorRate: 0,
    isLowConfidence: true,
    isHighErrorRate: false,
    start: async () => undefined,
    stop: async () => undefined,
    emitSignal: () => undefined,
  };
}

function usePredictiveLayerInternal(options: UsePredictiveLayerOptions = {}): PredictiveLayerContextValue {
  const {
    config,
    autoStart = true,
    confidenceThreshold = 0.3,
    errorRateThreshold = 0.1,
  } = options;

  const [layer, setLayer] = useState<PredictiveLayer | null>(null);
  const [snapshot, setSnapshot] = useState<PredictiveLayerSnapshot | null>(null);
  const [metrics, setMetrics] = useState<PredictiveMetrics | null>(null);
  const [isActive, setIsActive] = useState(false);

  useEffect(() => {
    const newLayer = new PredictiveLayer(config);
    setLayer(newLayer);

    if (autoStart) {
      newLayer.start();
      setIsActive(true);
    }

    return () => {
      newLayer.stop();
      setIsActive(false);
    };
  }, [config, autoStart]);

  useEffect(() => {
    if (!layer) return;

    const updateState = () => {
      setSnapshot(layer.getSnapshot());
      setMetrics(layer.getMetrics());
    };

    updateState();
    const interval = setInterval(updateState, 1000);
    return () => clearInterval(interval);
  }, [layer]);

  const confidence = useMemo(() => snapshot?.avgConfidence ?? 0, [snapshot]);
  const errorRate = useMemo(() => snapshot?.errorRate ?? 0, [snapshot]);
  const isLowConfidence = confidence < confidenceThreshold;
  const isHighErrorRate = errorRate > errorRateThreshold;

  const start = useCallback(async () => {
    if (!layer) return;
    layer.start();
    setIsActive(true);
    setSnapshot(layer.getSnapshot());
  }, [layer]);

  const stop = useCallback(async () => {
    if (!layer) return;
    layer.stop();
    setIsActive(false);
    setSnapshot(layer.getSnapshot());
  }, [layer]);

  const emitSignal = useCallback((signal: Signal) => {
    layer?.emitSignal(signal.node, signal.value, signal.metadata);
  }, [layer]);

  return {
    layer,
    isActive,
    snapshot,
    metrics,
    confidence,
    errorRate,
    isLowConfidence,
    isHighErrorRate,
    start,
    stop,
    emitSignal,
  };
}

export function usePredictiveLayer(options: UsePredictiveLayerOptions = {}): PredictiveLayerContextValue {
  const context = useContext(PredictiveLayerContext);
  return context ?? usePredictiveLayerInternal(options);
}

export interface PredictiveGuardStats {
  totalDecisions: number;
  blockedCount: number;
  warnedCount: number;
  proceededCount: number;
  accuracy: number;
  learnedActions: number;
}

export interface PredictiveGuardContextValue {
  guard: PredictiveGuard | null;
  isChecking: boolean;
  lastResult: SafetyCheckResult | null;
  stats: PredictiveGuardStats | null;
  checkSafety: (action: string, context: SafetyContext) => Promise<SafetyCheckResult>;
  canProceed: (action: string, context: SafetyContext) => Promise<boolean>;
  reportOutcome: (outcome: DecisionOutcome) => Promise<void>;
}

const PredictiveGuardContext = React.createContext<PredictiveGuardContextValue | null>(null);

export interface UsePredictiveGuardOptions {
  layer?: PredictiveLayer | null;
  config?: Partial<PredictiveGuardConfig>;
}

function createGuardNotInitializedResult(context: SafetyContext): SafetyCheckResult {
  return {
    safe: true,
    confidence: 0,
    successProbability: 0,
    riskLevel: 'medium',
    reason: `Predictive guard not initialized for ${context.action}. This is a neutral advisory state, not proof of safety.`,
    suggestedAction: 'review',
    similarPatterns: [],
    recentErrors: 0,
    traceId: '',
  };
}

function usePredictiveGuardInternal(options: UsePredictiveGuardOptions = {}): PredictiveGuardContextValue {
  const { layer, config } = options;
  const [guard, setGuard] = useState<PredictiveGuard | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [lastResult, setLastResult] = useState<SafetyCheckResult | null>(null);
  const [stats, setStats] = useState<PredictiveGuardStats | null>(null);

  useEffect(() => {
    if (!layer) {
      setGuard(null);
      setStats(null);
      return;
    }

    const newGuard = new PredictiveGuard(layer, config);
    setGuard(newGuard);
    setStats(newGuard.getStats());
  }, [layer, config]);

  useEffect(() => {
    if (!guard) return;

    const updateStats = () => setStats(guard.getStats());
    updateStats();
    const interval = setInterval(updateStats, 2000);
    return () => clearInterval(interval);
  }, [guard]);

  const checkSafety = useCallback(async (_action: string, context: SafetyContext): Promise<SafetyCheckResult> => {
    if (!guard) {
      const fallback = createGuardNotInitializedResult(context);
      setLastResult(fallback);
      return fallback;
    }

    setIsChecking(true);
    try {
      const result = await guard.checkSafety(context);
      setLastResult(result);
      setStats(guard.getStats());
      return result;
    } finally {
      setIsChecking(false);
    }
  }, [guard]);

  const canProceed = useCallback(async (action: string, context: SafetyContext): Promise<boolean> => {
    const result = await checkSafety(action, context);
    return result.suggestedAction !== 'block' && result.safe;
  }, [checkSafety]);

  const reportOutcome = useCallback(async (outcome: DecisionOutcome): Promise<void> => {
    if (!guard) return;
    await guard.reportDecisionOutcome(outcome);
    setStats(guard.getStats());
  }, [guard]);

  return {
    guard,
    isChecking,
    lastResult,
    stats,
    checkSafety,
    canProceed,
    reportOutcome,
  };
}

export function usePredictiveGuard(options: UsePredictiveGuardOptions = {}): PredictiveGuardContextValue {
  const context = useContext(PredictiveGuardContext);
  const layerContext = useContext(PredictiveLayerContext);
  return context ?? usePredictiveGuardInternal({ layer: options.layer ?? layerContext?.layer ?? null, config: options.config });
}

export interface PredictiveProviderProps {
  children: React.ReactNode;
  layerConfig?: PredictiveLayerConfig;
  guardConfig?: Partial<PredictiveGuardConfig>;
}

export function PredictiveProvider({ children, layerConfig, guardConfig }: PredictiveProviderProps) {
  const layerValue = usePredictiveLayerInternal({ config: layerConfig, autoStart: true });
  const guardValue = usePredictiveGuardInternal({ layer: layerValue.layer, config: guardConfig });

  return (
    <PredictiveLayerContext.Provider value={layerValue}>
      <PredictiveGuardContext.Provider value={guardValue}>
        {children}
      </PredictiveGuardContext.Provider>
    </PredictiveLayerContext.Provider>
  );
}

export function usePredictionConfidence(): { confidence: number; isLow: boolean; isHigh: boolean } {
  const { confidence, isLowConfidence, isHighErrorRate } = usePredictiveLayer();
  return {
    confidence,
    isLow: isLowConfidence,
    isHigh: isHighErrorRate,
  };
}

export function usePredictiveSignal() {
  const { emitSignal, isActive } = usePredictiveLayer();
  return {
    emitSignal,
    isActive,
  };
}

export { createNoLayerValue };
