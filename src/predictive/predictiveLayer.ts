/**
 * Predictive Layer
 *
 * Main orchestration class for the predictive coding layer.
 * Coordinates signal interception, prediction generation, error computation,
 * and Hebbian weight adaptation into a unified predictive coding cycle.
 *
 * @module predictive/predictiveLayer
 */

import type {
  Signal,
  Prediction,
  PredictionError,
  WeightUpdateResult,
  PredictiveLayerConfig,
  PredictiveLayerSnapshot,
  PredictiveCycleResult,
  NeuralNode,
  TraceId,
  PredictiveMetrics,
} from './types';

import {
  DEFAULT_PREDICTIVE_CONFIG,
  type PredictiveLayerSnapshot,
} from './types';

import { SignalBufferManager, DirectSignalEmitter, createDefaultSignalProxyConfig } from './signalProxy';
import { PredictionGenerator, createPredictionGenerator } from './predictionGenerator';
import { ErrorComputer, createErrorComputer } from './errorComputer';
import { HebbianAdaptor, createHebbianAdaptor, Synaptogenesis } from './hebbianAdaptor';
import { LatentSpaceNavigator, createLatentSpace } from './latentSpace';

// ============================================================================
// Trace ID Provider
// ============================================================================

let layerTraceSequence = 0;

function generateLayerTraceId(): string {
  layerTraceSequence = (layerTraceSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `pred-layer-${layerTraceSequence.toString(36).padStart(8, '0')}`;
}

// ============================================================================
// Predictive Layer
// ============================================================================

export interface PredictiveLayerEvents {
  onSignal?: (signals: Signal[]) => void;
  onPrediction?: (prediction: Prediction) => void;
  onError?: (error: PredictionError) => void;
  onWeightUpdate?: (updates: WeightUpdateResult[]) => void;
  onCycleComplete?: (result: PredictiveCycleResult) => void;
  onPhaseChange?: (phase: PredictiveLayerSnapshot['phase']) => void;
}

/**
 * Main Predictive Layer that orchestrates the predictive coding cycle.
 */
export class PredictiveLayer {
  private config: PredictiveLayerConfig;
  private enabled: boolean = false;
  private phase: PredictiveLayerSnapshot['phase'] = 'idle';
  
  // Core components
  private signalEmitter: DirectSignalEmitter;
  private signalBuffer: SignalBufferManager;
  private predictionGenerator: PredictionGenerator;
  private errorComputer: ErrorComputer;
  private hebbianAdaptor: HebbianAdaptor;
  private latentSpace: LatentSpaceNavigator;
  private synaptogenesis: Synaptogenesis;
  
  // Nodes and state
  private nodes: Map<string, NeuralNode> = new Map();
  
  // Event handlers
  private events: PredictiveLayerEvents = {};
  
  // Metrics
  private metrics: PredictiveMetrics = {
    signalInterceptionMs: 0,
    predictionGenerationMs: 0,
    errorComputationMs: 0,
    weightUpdateMs: 0,
    latentSpaceSearchMs: 0,
    totalCycleMs: 0,
  };
  
  // Flush interval
  private flushInterval: ReturnType<typeof setInterval> | null = null;

  constructor(config?: Partial<PredictiveLayerConfig>) {
    this.config = {
      ...DEFAULT_PREDICTIVE_CONFIG,
      ...config,
    };

    // Initialize components
    this.signalBuffer = new SignalBufferManager(this.config.signal.maxBufferSize);
    this.signalEmitter = new DirectSignalEmitter(
      this.config.signal.maxBufferSize,
      generateLayerTraceId,
    );
    this.latentSpace = createLatentSpace({
      dimension: this.config.latentSpace.dimension,
      maxPatterns: this.config.latentSpace.maxPatterns,
      similarityThreshold: this.config.latentSpace.similarityThreshold,
    });
    this.predictionGenerator = createPredictionGenerator(
      {},
      this.config,
    );
    this.errorComputer = createErrorComputer({
      threshold: this.config.error.threshold,
      propagationWeight: this.config.error.propagationWeight,
    });
    this.hebbianAdaptor = createHebbianAdaptor(this.config.hebbian);
    this.synaptogenesis = new Synaptogenesis({
      correlationThreshold: this.config.network.correlationThreshold,
      maxConnectionsPerNode: this.config.network.maxConnectionsPerNode,
    });
  }

  /**
   * Start the predictive layer.
   */
  start(): void {
    if (this.enabled) return;

    this.enabled = true;
    this.setPhase('idle');

    // Subscribe to signal batches
    this.signalEmitter.subscribe((signals) => {
      this.events.onSignal?.(signals);
    });

    // Start flush interval
    if (this.config.signal.flushIntervalMs > 0) {
      this.flushInterval = setInterval(() => {
        this.processSignalBatch();
      }, this.config.signal.flushIntervalMs);
    }
  }

  /**
   * Stop the predictive layer.
   */
  stop(): void {
    this.enabled = false;
    this.setPhase('idle');

    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = null;
    }
  }

  /**
   * Process a single signal through the predictive coding cycle.
   */
  async processSignal(signal: Signal): Promise<PredictiveCycleResult> {
    if (!this.enabled) {
      return this.createEmptyResult(signal);
    }

    const startTime = performance.now();
    this.setPhase('predicting');

    try {
      // Step 1: Generate prediction
      const predictionStart = performance.now();
      const prediction = await this.predictionGenerator.generatePrediction(
        signal,
        signal.traceId,
      );
      this.metrics.predictionGenerationMs = performance.now() - predictionStart;
      
      this.events.onPrediction?.(prediction);

      // Step 2: Compute error
      this.setPhase('error-computing');
      const errorStart = performance.now();
      const error = this.errorComputer.computeError(signal, prediction, signal.traceId);
      this.metrics.errorComputationMs = performance.now() - errorStart;
      
      this.events.onError?.(error);

      // Step 3: Learn from prediction and update weights (if error propagated)
      this.setPhase('learning');
      const weightStart = performance.now();
      let weightUpdates: WeightUpdateResult[] = [];

      if (error.propagated) {
        // Update latent space
        this.latentSpace.addPattern({
          id: `pattern-${signal.id}`,
          embedding: this.createEmbedding(signal.value),
          norm: this.computeNorm(this.createEmbedding(signal.value)),
          signalValue: signal.value,
          node: signal.node,
          createdAt: Date.now(),
          matchCount: 1,
          avgConfidence: prediction.confidence,
        });

        // Update Hebbian weights
        const node = this.nodes.get(signal.node);
        if (node) {
          for (const synapse of node.incomingSynapses) {
            const sourceNode = this.nodes.get(synapse.sourceNode);
            if (sourceNode) {
              const result = this.hebbianAdaptor.updateWeight(
                synapse.id,
                error,
                sourceNode.activation,
              );
              if (result) {
                weightUpdates.push(result);
              }
            }
          }
        }
      }
      
      this.metrics.weightUpdateMs = performance.now() - weightStart;
      this.events.onWeightUpdate?.(weightUpdates);

      // Complete cycle
      this.setPhase('idle');
      const totalDuration = performance.now() - startTime;
      this.metrics.totalCycleMs = totalDuration;

      const result: PredictiveCycleResult = {
        prediction,
        error,
        weightUpdates,
        latentSpaceUpdates: [],
        predictionAccurate: !error.propagated,
        durationMs: totalDuration,
      };

      this.events.onCycleComplete?.(result);

      return result;
    } catch (error) {
      this.setPhase('idle');
      throw error;
    }
  }

  /**
   * Process a batch of signals.
   */
  async processSignalBatch(): Promise<PredictiveCycleResult[]> {
    if (!this.enabled) return [];

    const signals = this.signalEmitter.flush();
    if (signals.length === 0) return [];

    const results: PredictiveCycleResult[] = [];
    for (const signal of signals) {
      const result = await this.processSignal(signal);
      results.push(result);
    }

    return results;
  }

  /**
   * Emit a signal directly.
   */
  emitSignal(
    node: string,
    value: number,
    metadata?: Record<string, unknown>,
  ): Signal {
    const signal = this.signalEmitter.emit(node, value, metadata);
    
    if (this.enabled) {
      // Process immediately if enabled
      this.processSignal(signal);
    }
    
    return signal;
  }

  /**
   * Register a neural node.
   */
  registerNode(node: NeuralNode): void {
    this.nodes.set(node.id, node);
    this.predictionGenerator.registerNode(node);
    this.hebbianAdaptor.registerNode(node);
  }

  /**
   * Set event handlers.
   */
  setEvents(events: PredictiveLayerEvents): void {
    this.events = { ...this.events, ...events };
  }

  /**
   * Get current snapshot of the layer state.
   */
  getSnapshot(): PredictiveLayerSnapshot {
    const patternCount = this.latentSpace.getPatternCount();
    const synapseCount = this.hebbianAdaptor.getSynapses().length;
    const errorStats = this.errorComputer.getStats();
    
    const avgConfidence = this.predictionGenerator.getStats().avgConfidence;
    const errorRate = errorStats.totalErrors > 0
      ? errorStats.propagatedErrors / errorStats.totalErrors
      : 0;

    return {
      active: this.enabled,
      phase: this.phase,
      nodeCount: this.nodes.size,
      synapseCount,
      patternCount,
      avgConfidence,
      errorRate,
      memoryUsageBytes: this.estimateMemoryUsage(),
      timestamp: Date.now(),
    };
  }

  /**
   * Get performance metrics.
   */
  getMetrics(): PredictiveMetrics {
    return { ...this.metrics };
  }

  /**
   * Get prediction generator.
   */
  getPredictionGenerator(): PredictionGenerator {
    return this.predictionGenerator;
  }

  /**
   * Get error computer.
   */
  getErrorComputer(): ErrorComputer {
    return this.errorComputer;
  }

  /**
   * Get Hebbian adaptor.
   */
  getHebbianAdaptor(): HebbianAdaptor {
    return this.hebbianAdaptor;
  }

  /**
   * Get latent space navigator.
   */
  getLatentSpace(): LatentSpaceNavigator {
    return this.latentSpace;
  }

  /**
   * Check if layer is enabled.
   */
  isEnabled(): boolean {
    return this.enabled;
  }

  /**
   * Get current phase.
   */
  getPhase(): PredictiveLayerSnapshot['phase'] {
    return this.phase;
  }

  /**
   * Enable or disable the layer.
   */
  setEnabled(enabled: boolean): void {
    if (enabled) {
      this.start();
    } else {
      this.stop();
    }
  }

  /**
   * Reset all state.
   */
  reset(): void {
    this.signalEmitter.clear();
    this.signalBuffer.clear();
    this.predictionGenerator.clearHistory();
    this.errorComputer.reset();
    this.hebbianAdaptor.clear();
    this.latentSpace.clear();
    this.synaptogenesis.clear();
    this.nodes.clear();
    
    this.metrics = {
      signalInterceptionMs: 0,
      predictionGenerationMs: 0,
      errorComputationMs: 0,
      weightUpdateMs: 0,
      latentSpaceSearchMs: 0,
      totalCycleMs: 0,
    };
  }

  // --------------------------------------------------------------------------
  // Private Methods
  // --------------------------------------------------------------------------

  private setPhase(phase: PredictiveLayerSnapshot['phase']): void {
    if (this.phase !== phase) {
      this.phase = phase;
      this.events.onPhaseChange?.(phase);
    }
  }

  private createEmptyResult(signal: Signal): PredictiveCycleResult {
    return {
      prediction: {
        id: `empty-${signal.id}`,
        predictedValue: signal.value,
        confidence: 0,
        node: signal.node,
        timestamp: Date.now(),
        traceId: signal.traceId,
      },
      error: {
        id: `empty-err-${signal.id}`,
        actual: signal.value,
        predicted: signal.value,
        error: 0,
        absoluteError: 0,
        propagated: false,
        node: signal.node,
        timestamp: Date.now(),
        traceId: signal.traceId,
        weight: 0,
      },
      weightUpdates: [],
      latentSpaceUpdates: [],
      predictionAccurate: true,
      durationMs: 0,
    };
  }

  private createEmbedding(value: number): number[] {
    const embedding: number[] = [];
    for (let i = 0; i < this.config.latentSpace.dimension; i++) {
      const s = value * (i + 1) * 7919;
      embedding.push((Math.sin(s) + 1) / 2);
    }
    return embedding;
  }

  private computeNorm(vector: number[]): number {
    return Math.sqrt(vector.reduce((sum, v) => sum + v * v, 0));
  }

  private estimateMemoryUsage(): number {
    return (
      this.latentSpace.estimateMemoryUsage() +
      this.signalEmitter.getPendingCount() * 200 + // ~200 bytes per signal
      this.hebbianAdaptor.getSynapses().length * 100 // ~100 bytes per synapse
    );
  }
}

// ============================================================================
// Default Instance
// ============================================================================

let defaultLayerInstance: PredictiveLayer | null = null;

/**
 * Get the default predictive layer instance.
 */
export function getDefaultPredictiveLayer(): PredictiveLayer {
  if (!defaultLayerInstance) {
    defaultLayerInstance = new PredictiveLayer();
  }
  return defaultLayerInstance;
}

/**
 * Create a new predictive layer with optional config.
 */
export function createPredictiveLayer(
  config?: Partial<PredictiveLayerConfig>,
): PredictiveLayer {
  return new PredictiveLayer(config);
}

// ============================================================================
// Module Exports
// ============================================================================

export type { PredictiveLayerEvents } from './predictiveLayer';
