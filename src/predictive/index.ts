/**
 * Predictive Coding Layer - Public Exports
 *
 * Main entry point for the predictive coding layer module.
 * Provides biologically-inspired predictive intelligence for the runtime system.
 *
 * @module predictive
 */

// ============================================================================
// Types
// ============================================================================

export {
  // Core types
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
  // Validation functions
  isValidSignal,
  isValidPrediction,
  isValidSynapse,
  // Default configurations
  DEFAULT_HEBBIAN_CONFIG,
  DEFAULT_PREDICTIVE_CONFIG,
} from './types';

// ============================================================================
// Predictive Guard (Phase 4.1)
// ============================================================================

export {
  type SafetyContext,
  type SafetyCheckResult,
  type SafetyLevel,
  type PredictiveGuardConfig,
  type GuardThresholds,
  type DecisionOutcome,
  type SimilarPattern,
  PredictiveGuard,
  createPredictiveGuard,
} from './predictiveGuard';

// ============================================================================
// Safety Check Functions (Phase 4.2)
// ============================================================================

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
} from './predictiveSafety';

// ============================================================================
// Predictive Guard Hooks (Phase 4.4)
// ============================================================================

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

// ============================================================================
// RuntimeIntelligence Integration (Phase 4.3)
// ============================================================================

export {
  createPredictiveRuntimeGuard,
  createBuildPredictiveGuard,
  createPublishPredictiveGuard,
  createDecisionPredictiveGuard,
  createSystemHealthPredictiveGuard,
  createPredictiveGuardChain,
  type PredictiveRuntimeGuardOptions,
} from './runtimeIntelligenceIntegration';

// ============================================================================
// UI Components (Phase 4.4)
// ============================================================================

export { PredictiveUI, PredictiveConfidenceBar, PredictiveStatusBadge, PredictiveHealthIndicator, PredictiveWarningToast, PredictiveDecisionOverlay } from './ui/PredictiveUI';
// ============================================================================

export {
  type SignalEmitter,
  type SignalProxyInstance,
  SignalBufferManager,
  createSignalProxy,
  DirectSignalEmitter,
  createDefaultSignalProxyConfig,
} from './signalProxy';

// ============================================================================
// Prediction Generator
// ============================================================================

export {
  type PredictionGeneratorOptions,
  PredictionGenerator,
  createPredictionGenerator,
} from './predictionGenerator';

// ============================================================================
// Latent Space Navigator
// ============================================================================

export {
  type LatentSpaceConfig,
  type LatentSpaceSearchOptions,
  LatentSpaceNavigator,
  createLatentSpace,
} from './latentSpace';

// ============================================================================
// Error Computer
// ============================================================================

export {
  type ErrorComputerConfig,
  type ErrorStats,
  ErrorComputer,
  createErrorComputer,
  calculateAccuracy,
  calculateMSE,
  calculateRMSE,
} from './errorComputer';

// ============================================================================
// Hebbian Adaptor
// ============================================================================

export {
  type HebbianAdaptorStats,
  type SynaptogenesisConfig,
  HebbianAdaptor,
  Synaptogenesis,
  createHebbianAdaptor,
} from './hebbianAdaptor';

// ============================================================================
// Predictive Layer (Main Class)
// ============================================================================

export {
  type PredictiveLayerEvents,
  PredictiveLayer,
  getDefaultPredictiveLayer,
  createPredictiveLayer,
} from './predictiveLayer';

// ============================================================================
// Nociceptor Error Boundary
// ============================================================================

export {
  type NociceptorErrorBoundaryProps,
  type ErrorContext,
  type PainSignal,
  NociceptorErrorBoundary,
  withNociceptor,
  getPainSeverityLabel,
  formatPainSignal,
} from './nociceptorBoundary';

// ============================================================================
// Quick Start Factory
// ============================================================================

import { PredictiveLayer, createPredictiveLayer } from './predictiveLayer';
import { DEFAULT_PREDICTIVE_CONFIG } from './types';

/**
 * Quick start: Create a configured predictive layer.
 * 
 * @example
 * ```typescript
 * import { createQuickPredictiveLayer } from './predictive';
 * 
 * const layer = createQuickPredictiveLayer();
 * layer.start();
 * 
 * // Emit signals
 * layer.emitSignal('runtime.decision', 0.85, { type: 'container_decision' });
 * layer.emitSignal('runtime.error_rate', 0.05, { type: 'telemetry' });
 * ```
 */
export function createQuickPredictiveLayer(): PredictiveLayer {
  return createPredictiveLayer(DEFAULT_PREDICTIVE_CONFIG);
}

// ============================================================================
// React Hook (for easy integration)
// ============================================================================

import { useEffect, useState, useRef, useCallback } from 'react';
import type { PredictiveLayerSnapshot, Signal } from './types';

/**
 * React hook for using the predictive layer.
 * 
 * @example
 * ```typescript
 * import { usePredictiveLayer } from './predictive';
 * 
 * function MyComponent() {
 *   const { layer, snapshot, emit } = usePredictiveLayer();
 *   
 *   const handleDecision = () => {
 *     emit('runtime.decision', 0.85);
 *   };
 *   
 *   return (
 *     <div>
 *       <p>Confidence: {snapshot.avgConfidence.toFixed(2)}</p>
 *       <button onClick={handleDecision}>Make Decision</button>
 *     </div>
 *   );
 * }
 * ```
 */
export function usePredictiveLayer() {
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

  // Initialize layer
  useEffect(() => {
    if (!layerRef.current) {
      layerRef.current = createPredictiveLayer();
      layerRef.current.setEvents({
        onSignal: (signals) => {
          setEvents((prev) => [...prev, ...signals].slice(-100));
        },
      });
    }

    const layer = layerRef.current;
    layer.start();

    // Update snapshot periodically
    const interval = setInterval(() => {
      setSnapshot(layer.getSnapshot());
    }, 1000);

    return () => {
      clearInterval(interval);
      layer.stop();
    };
  }, []);

  // Emit a signal
  const emit = useCallback((node: string, value: number, metadata?: Record<string, unknown>) => {
    if (layerRef.current) {
      return layerRef.current.emitSignal(node, value, metadata);
    }
    return null;
  }, []);

  // Get layer instance
  const getLayer = useCallback(() => layerRef.current, []);

  return {
    layer: layerRef.current,
    snapshot,
    events,
    emit,
    getLayer,
  };
}
