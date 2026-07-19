/**
 * Predictive Coding Layer - Public Exports
 *
 * Main entry point for the predictive coding layer module.
 * Provides biologically-inspired predictive intelligence for the runtime system.
 *
 * @module predictive
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { PredictiveLayer, createPredictiveLayer } from './predictiveLayer';
import { DEFAULT_PREDICTIVE_CONFIG, type PredictiveLayerSnapshot, type Signal } from './types';

export {
  type Signal,
  type Prediction,
  type PredictionError,
  type Synapse,
  type NeuralNode,
  type NodeType,
  type HebbianConfig,
  type WeightUpdateResult,
  type PatternEmbedding,
  type SimilarityMatch,
  type SignalBuffer,
  type SignalProxyConfig,
  type PredictiveLayerConfig,
  type PredictiveLayerSnapshot,
  type PredictiveCycleResult,
  type PredictiveTelemetryEvent,
  type PredictiveMetrics,
  type TraceId,
  isValidSignal,
  isValidPrediction,
  isValidSynapse,
  DEFAULT_HEBBIAN_CONFIG,
  DEFAULT_PREDICTIVE_CONFIG,
} from './types';

export {
  type SafetyContext,
  type SafetyCheckResult,
  type PredictiveGuardConfig,
  type GuardThresholds,
  type DecisionOutcome,
  type SimilarPattern,
  PredictiveGuard,
  createPredictiveGuard,
} from './predictiveGuard';

export {
  DEFAULT_SAFETY_THRESHOLDS,
  checkActionSafety,
  checkBuildSafety,
  checkPublishSafety,
  checkDecisionSafety,
  getSystemSafetyStatus,
  safetyCheckToGuardResult,
  predictiveGuardPreFlight,
  type ActionSafetyCheck,
  type SimilarFailure,
  type RuntimeSafetyContext,
  type SafetyLevel,
} from './predictiveSafety';

export {
  usePredictiveLayer,
  usePredictiveGuard,
  usePredictionConfidence,
  usePredictiveSignal,
  PredictiveProvider,
  type PredictiveLayerContextValue,
  type UsePredictiveLayerOptions,
  type PredictiveGuardContextValue,
  type UsePredictiveGuardOptions,
  type PredictiveProviderProps,
} from './predictiveHooks';

export {
  createPredictiveRuntimeGuard,
  createBuildPredictiveGuard,
  createPublishPredictiveGuard,
  createDecisionPredictiveGuard,
  createSystemHealthPredictiveGuard,
  createPredictiveGuardChainForAction,
  createPredictiveGuardChain,
  type PredictiveGuardAction,
  type PredictiveRuntimeGuardOptions,
} from './runtimeIntelligenceIntegration';

export {
  PredictiveUI,
  PredictiveConfidenceBar,
  PredictiveStatusBadge,
  PredictiveHealthIndicator,
  PredictiveWarningToast,
  PredictiveDecisionOverlay,
} from './ui/PredictiveUI';

export {
  type SignalEmitter,
  type SignalProxyInstance,
  SignalBufferManager,
  createSignalProxy,
  DirectSignalEmitter,
  createDefaultSignalProxyConfig,
} from './signalProxy';

export {
  type PredictionGeneratorOptions,
  PredictionGenerator,
  createPredictionGenerator,
} from './predictionGenerator';

export {
  type LatentSpaceConfig,
  type LatentSpaceSearchOptions,
  LatentSpaceNavigator,
  createLatentSpace,
} from './latentSpace';

export {
  type ErrorComputerConfig,
  type ErrorStats,
  ErrorComputer,
  createErrorComputer,
  calculateAccuracy,
  calculateMSE,
  calculateRMSE,
} from './errorComputer';

export {
  type HebbianAdaptorStats,
  type HebbianMathTrace,
  type SynaptogenesisConfig,
  HebbianAdaptor,
  Synaptogenesis,
  createHebbianAdaptor,
  calculatePredictionGradient,
  calculateErrorDrivenDelta,
  calculateExtendedHebbianDelta,
  applyHebbianDamping,
  applyHebbianDecay,
  calculateHebbianMathTrace,
  calculateCoActivationDelta,
} from './hebbianAdaptor';

export {
  type PredictiveLayerEvents,
  PredictiveLayer,
  getDefaultPredictiveLayer,
  createPredictiveLayer,
} from './predictiveLayer';

export {
  type NociceptorErrorBoundaryProps,
  type ErrorContext,
  type PainSignal,
  NociceptorErrorBoundary,
  withNociceptor,
  getPainSeverityLabel,
  formatPainSignal,
} from './nociceptorBoundary';

export function createQuickPredictiveLayer(): PredictiveLayer {
  return createPredictiveLayer(DEFAULT_PREDICTIVE_CONFIG);
}

/**
 * Standalone hook for isolated predictive experiments. Product UI should prefer
 * PredictiveProvider + usePredictiveLayer from predictiveHooks.
 */
export function useStandalonePredictiveLayer() {
  const layerRef = useRef<PredictiveLayer | null>(null);
  const [snapshot, setSnapshot] = useState<PredictiveLayerSnapshot>(() => ({
    active: false,
    phase: 'idle',
    nodeCount: 0,
    synapseCount: 0,
    patternCount: 0,
    avgConfidence: 0,
    errorRate: 0,
    memoryUsageBytes: 0,
    timestamp: Date.now(),
  }));
  const [events, setEvents] = useState<Signal[]>([]);

  useEffect(() => {
    if (!layerRef.current) {
      layerRef.current = createPredictiveLayer();
      layerRef.current.setEvents({
        onSignal: (signals) => setEvents((prev) => [...prev, ...signals].slice(-100)),
      });
    }

    const layer = layerRef.current;
    layer.start();
    const interval = setInterval(() => setSnapshot(layer.getSnapshot()), 1000);

    return () => {
      clearInterval(interval);
      layer.stop();
    };
  }, []);

  const emit = useCallback((node: string, value: number, metadata?: Record<string, unknown>) => {
    return layerRef.current?.emitSignal(node, value, metadata) ?? null;
  }, []);

  const getLayer = useCallback(() => layerRef.current, []);

  return {
    layer: layerRef.current,
    snapshot,
    events,
    emit,
    getLayer,
  };
}
