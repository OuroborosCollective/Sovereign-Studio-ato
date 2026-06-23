/**
 * Predictive Layer React Hooks
 *
 * React hooks for integrating the predictive layer with UI components.
 *
 * @module predictive/predictiveHooks
 */

import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { PredictiveGuard, PredictiveGuardConfig, SafetyContext, SafetyCheckResult, DecisionOutcome } from './predictiveGuard';
import { PredictiveLayer, PredictiveLayerSnapshot, PredictiveMetrics } from './predictiveLayer';

// ============================================================================
// Predictive Layer Context
// ============================================================================

export interface PredictiveLayerContextValue {
  /** The predictive layer instance */
  layer: PredictiveLayer | null;
  /** Whether the layer is active */
  isActive: boolean;
  /** Current snapshot of the layer state */
  snapshot: PredictiveLayerSnapshot | null;
  /** Current metrics */
  metrics: PredictiveMetrics | null;
  /** Average confidence [0, 1] */
  confidence: number;
  /** Current error rate [0, 1] */
  errorRate: number;
  /** Whether confidence is below threshold */
  isLowConfidence: boolean;
  /** Whether error rate is above threshold */
  isHighErrorRate: boolean;
  /** Start the predictive layer */
  start: () => Promise<void>;
  /** Stop the predictive layer */
  stop: () => Promise<void>;
  /** Emit a signal */
  emitSignal: (signal: import('./types').Signal) => void;
}

const PredictiveLayerContext = React.createContext<PredictiveLayerContextValue | null>(null);

export interface UsePredictiveLayerOptions {
  /** Initial config for the predictive layer */
  config?: import('./predictiveLayer').PredictiveLayerConfig;
  /** Auto-start on mount */
  autoStart?: boolean;
  /** Confidence threshold for isLowConfidence */
  confidenceThreshold?: number;
  /** Error rate threshold for isHighErrorRate */
  errorRateThreshold?: number;
}

/**
 * Hook to access the predictive layer.
 */
export function usePredictiveLayer(options: UsePredictiveLayerOptions = {}): PredictiveLayerContextValue {
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

  // Initialize the predictive layer
  useEffect(() => {
    const initLayer = async () => {
      const newLayer = new PredictiveLayer(config);
      setLayer(newLayer);

      if (autoStart) {
        await newLayer.start();
        setIsActive(true);
      }
    };

    initLayer();

    return () => {
      if (layer) {
        layer.stop().catch(console.error);
      }
    };
  }, []);

  // Update snapshot and metrics periodically
  useEffect(() => {
    if (!layer) return;

    const updateState = () => {
      const newSnapshot = layer.getSnapshot();
      const newMetrics = layer.getMetrics();
      setSnapshot(newSnapshot);
      setMetrics(newMetrics);
    };

    updateState();
    const interval = setInterval(updateState, 1000);

    return () => clearInterval(interval);
  }, [layer]);

  // Computed values
  const confidence = useMemo(() => {
    if (!snapshot) return 0;
    return snapshot.nodes.length > 0
      ? snapshot.nodes.reduce((sum, n) => sum + n.confidence, 0) / snapshot.nodes.length
      : 0;
  }, [snapshot]);

  const errorRate = useMemo(() => {
    if (!metrics || metrics.totalPredictions === 0) return 0;
    return metrics.failedPredictions / metrics.totalPredictions;
  }, [metrics]);

  const isLowConfidence = confidence < confidenceThreshold;
  const isHighErrorRate = errorRate > errorRateThreshold;

  // Methods
  const start = useCallback(async () => {
    if (layer) {
      await layer.start();
      setIsActive(true);
    }
  }, [layer]);

  const stop = useCallback(async () => {
    if (layer) {
      await layer.stop();
      setIsActive(false);
    }
  }, [layer]);

  const emitSignal = useCallback((signal: import('./types').Signal) => {
    if (layer) {
      layer.emitSignal(signal);
    }
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

// ============================================================================
// Predictive Guard Context
// ============================================================================

export interface PredictiveGuardContextValue {
  /** The guard instance */
  guard: PredictiveGuard | null;
  /** Whether currently checking */
  isChecking: boolean;
  /** Last check result */
  lastResult: SafetyCheckResult | null;
  /** Guard statistics */
  stats: { totalDecisions: number; blockedCount: number; warnedCount: number; accuracy: number } | null;
  /** Check safety for an action */
  checkSafety: (action: string, context: SafetyContext) => Promise<SafetyCheckResult>;
  /** Whether can proceed with action */
  canProceed: (action: string, context: SafetyContext) => Promise<boolean>;
  /** Report outcome of a decision */
  reportOutcome: (outcome: DecisionOutcome) => Promise<void>;
}

const PredictiveGuardContext = React.createContext<PredictiveGuardContextValue | null>(null);

export interface UsePredictiveGuardOptions {
  /** The predictive layer to use */
  layer: PredictiveLayer | null;
  /** Guard configuration */
  config?: Partial<PredictiveGuardConfig>;
}

/**
 * Hook to use the predictive guard.
 */
export function usePredictiveGuard(options: UsePredictiveGuardOptions = {}): PredictiveGuardContextValue {
  const { layer, config } = options;

  const [guard, setGuard] = useState<PredictiveGuard | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [lastResult, setLastResult] = useState<SafetyCheckResult | null>(null);
  const [stats, setStats] = useState<{ totalDecisions: number; blockedCount: number; warnedCount: number; accuracy: number } | null>(null);

  // Initialize guard when layer is available
  useEffect(() => {
    if (layer) {
      const newGuard = new PredictiveGuard(layer, config);
      setGuard(newGuard);

      // Get initial stats
      const guardStats = newGuard.getStats();
      setStats(guardStats);
    }
  }, [layer, config]);

  // Update stats periodically
  useEffect(() => {
    if (!guard) return;

    const updateStats = () => {
      const guardStats = guard.getStats();
      setStats(guardStats);
    };

    updateStats();
    const interval = setInterval(updateStats, 2000);

    return () => clearInterval(interval);
  }, [guard]);

  const checkSafety = useCallback(async (action: string, context: SafetyContext): Promise<SafetyCheckResult> => {
    if (!guard) {
      return {
        safe: true,
        confidence: 1,
        successProbability: 1,
        riskLevel: 'low',
        reason: 'Guard not initialized',
        suggestedAction: 'proceed',
        similarPatterns: [],
        recentErrors: 0,
        traceId: '',
      };
    }

    setIsChecking(true);
    try {
      const result = await guard.checkSafety(context);
      setLastResult(result);
      
      const guardStats = guard.getStats();
      setStats(guardStats);
      
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
    if (guard) {
      await guard.reportDecisionOutcome(outcome);
      const guardStats = guard.getStats();
      setStats(guardStats);
    }
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

// ============================================================================
// Combined Provider
// ============================================================================

export interface PredictiveProviderProps {
  children: React.ReactNode;
  layerConfig?: import('./predictiveLayer').PredictiveLayerConfig;
  guardConfig?: Partial<PredictiveGuardConfig>;
}

export function PredictiveProvider({ children, layerConfig, guardConfig }: PredictiveProviderProps) {
  const layerValue = usePredictiveLayer({ config: layerConfig, autoStart: true });
  const guardValue = usePredictiveGuard({ layer: layerValue.layer, config: guardConfig });

  return (
    <PredictiveLayerContext.Provider value={layerValue}>
      <PredictiveGuardContext.Provider value={guardValue}>
        {children}
      </PredictiveGuardContext.Provider>
    </PredictiveLayerContext.Provider>
  );
}

// ============================================================================
// Convenience Hooks
// ============================================================================

/**
 * Simple hook for checking if predictions are reliable.
 */
export function usePredictionConfidence(): { confidence: number; isLow: boolean; isHigh: boolean } {
  const { confidence, isLowConfidence, isHighErrorRate } = usePredictiveLayer();
  return {
    confidence,
    isLow: isLowConfidence,
    isHigh: isHighErrorRate,
  };
}

/**
 * Hook for emitting signals to the predictive layer.
 */
export function usePredictiveSignal() {
  const { emitSignal, isActive } = usePredictiveLayer();

  return {
    emitSignal,
    isActive,
  };
}
