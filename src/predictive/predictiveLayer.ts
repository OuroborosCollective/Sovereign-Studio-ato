/**
 * Predictive Layer
 *
 * Main orchestration class for the predictive coding layer. It coordinates
 * runtime signals, prediction generation, error computation and adaptive
 * weights. The resulting state is advisory and must be validated by hard
 * runtime guards before user-visible actions proceed.
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
  PredictiveMetrics,
} from './types';

import { DEFAULT_PREDICTIVE_CONFIG } from './types';
import { SignalBufferManager, DirectSignalEmitter } from './signalProxy';
import { PredictionGenerator, createPredictionGenerator } from './predictionGenerator';
import { ErrorComputer, createErrorComputer } from './errorComputer';
import { HebbianAdaptor, createHebbianAdaptor, Synaptogenesis } from './hebbianAdaptor';
import { LatentSpaceNavigator, createLatentSpace } from './latentSpace';

let layerTraceSequence = 0;

function generateLayerTraceId(): string {
  layerTraceSequence = (layerTraceSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `pred-layer-${layerTraceSequence.toString(36).padStart(8, '0')}`;
}

export interface PredictiveLayerEvents {
  onSignal?: (signals: Signal[]) => void;
  onPrediction?: (prediction: Prediction) => void;
  onError?: (error: PredictionError) => void;
  onWeightUpdate?: (updates: WeightUpdateResult[]) => void;
  onCycleComplete?: (result: PredictiveCycleResult) => void;
  onPhaseChange?: (phase: PredictiveLayerSnapshot['phase']) => void;
}

export class PredictiveLayer {
  private config: PredictiveLayerConfig;
  private enabled = false;
  private phase: PredictiveLayerSnapshot['phase'] = 'idle';
  private signalEmitter: DirectSignalEmitter;
  private signalBuffer: SignalBufferManager;
  private predictionGenerator: PredictionGenerator;
  private errorComputer: ErrorComputer;
  private hebbianAdaptor: HebbianAdaptor;
  private latentSpace: LatentSpaceNavigator;
  private synaptogenesis: Synaptogenesis;
  private nodes: Map<string, NeuralNode> = new Map();
  private events: PredictiveLayerEvents = {};
  private metrics: PredictiveMetrics = {
    signalInterceptionMs: 0,
    predictionGenerationMs: 0,
    errorComputationMs: 0,
    weightUpdateMs: 0,
    latentSpaceSearchMs: 0,
    totalCycleMs: 0,
  };
  private flushInterval: ReturnType<typeof setInterval> | null = null;

  constructor(config?: Partial<PredictiveLayerConfig>) {
    this.config = {
      ...DEFAULT_PREDICTIVE_CONFIG,
      ...config,
      hebbian: { ...DEFAULT_PREDICTIVE_CONFIG.hebbian, ...(config?.hebbian ?? {}) },
      signal: { ...DEFAULT_PREDICTIVE_CONFIG.signal, ...(config?.signal ?? {}) },
      latentSpace: { ...DEFAULT_PREDICTIVE_CONFIG.latentSpace, ...(config?.latentSpace ?? {}) },
      network: { ...DEFAULT_PREDICTIVE_CONFIG.network, ...(config?.network ?? {}) },
      error: { ...DEFAULT_PREDICTIVE_CONFIG.error, ...(config?.error ?? {}) },
      worker: { ...DEFAULT_PREDICTIVE_CONFIG.worker, ...(config?.worker ?? {}) },
    };

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
    this.predictionGenerator = createPredictionGenerator({}, this.config);
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

  start(): void {
    if (this.enabled) return;

    this.enabled = true;
    this.setPhase('idle');
    this.signalEmitter.subscribe((signals) => {
      this.events.onSignal?.(signals);
    });

    if (this.config.signal.flushIntervalMs > 0) {
      this.flushInterval = setInterval(() => {
        void this.processSignalBatch();
      }, this.config.signal.flushIntervalMs);
    }
  }

  stop(): void {
    this.enabled = false;
    this.setPhase('idle');

    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = null;
    }
  }

  async processSignal(signal: Signal): Promise<PredictiveCycleResult> {
    if (!this.enabled) return this.createEmptyResult(signal);

    const startTime = performance.now();
    this.setPhase('predicting');

    try {
      const predictionStart = performance.now();
      const prediction = await this.predictionGenerator.generatePrediction(signal, signal.traceId);
      this.metrics.predictionGenerationMs = performance.now() - predictionStart;
      this.events.onPrediction?.(prediction);

      this.setPhase('error-computing');
      const errorStart = performance.now();
      const error = this.errorComputer.computeError(signal, prediction, signal.traceId);
      this.metrics.errorComputationMs = performance.now() - errorStart;
      this.events.onError?.(error);

      this.setPhase('learning');
      const weightStart = performance.now();
      const weightUpdates: WeightUpdateResult[] = [];

      if (error.propagated) {
        const embedding = this.createEmbedding(signal.value);
        this.latentSpace.addPattern({
          id: `pattern-${signal.id}`,
          embedding,
          norm: this.computeNorm(embedding),
          signalValue: signal.value,
          node: signal.node,
          createdAt: Date.now(),
          matchCount: 1,
          avgConfidence: prediction.confidence,
        });

        const node = this.nodes.get(signal.node);
        if (node) {
          for (const synapse of node.incomingSynapses) {
            const sourceNode = this.nodes.get(synapse.sourceNode);
            if (!sourceNode) continue;
            const result = this.hebbianAdaptor.updateWeight(synapse.id, error, sourceNode.activation);
            if (result) weightUpdates.push(result);
          }
        }
      }

      this.metrics.weightUpdateMs = performance.now() - weightStart;
      this.events.onWeightUpdate?.(weightUpdates);

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

  async processSignalBatch(): Promise<PredictiveCycleResult[]> {
    if (!this.enabled) return [];

    const signals = this.signalEmitter.flush();
    if (signals.length === 0) return [];

    const results: PredictiveCycleResult[] = [];
    for (const signal of signals) {
      results.push(await this.processSignal(signal));
    }

    return results;
  }

  emitSignal(node: string, value: number, metadata?: Record<string, unknown>): Signal {
    const signal = this.signalEmitter.emit(node, value, metadata);
    if (this.enabled) void this.processSignal(signal);
    return signal;
  }

  registerNode(node: NeuralNode): void {
    this.nodes.set(node.id, node);
    this.predictionGenerator.registerNode(node);
    this.hebbianAdaptor.registerNode(node);
  }

  setEvents(events: PredictiveLayerEvents): void {
    this.events = { ...this.events, ...events };
  }

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

  getMetrics(): PredictiveMetrics {
    return { ...this.metrics };
  }

  getPredictionGenerator(): PredictionGenerator {
    return this.predictionGenerator;
  }

  getErrorComputer(): ErrorComputer {
    return this.errorComputer;
  }

  getHebbianAdaptor(): HebbianAdaptor {
    return this.hebbianAdaptor;
  }

  getLatentSpace(): LatentSpaceNavigator {
    return this.latentSpace;
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  getPhase(): PredictiveLayerSnapshot['phase'] {
    return this.phase;
  }

  setEnabled(enabled: boolean): void {
    if (enabled) this.start();
    else this.stop();
  }

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
    for (let i = 0; i < this.config.latentSpace.dimension; i += 1) {
      const s = value * (i + 1) * 7919;
      embedding.push((Math.sin(s) + 1) / 2);
    }
    return embedding;
  }

  private computeNorm(vector: number[]): number {
    return Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0));
  }

  private estimateMemoryUsage(): number {
    return (
      this.latentSpace.estimateMemoryUsage() +
      this.signalEmitter.getPendingCount() * 200 +
      this.hebbianAdaptor.getSynapses().length * 100
    );
  }
}

let defaultLayerInstance: PredictiveLayer | null = null;

export function getDefaultPredictiveLayer(): PredictiveLayer {
  if (!defaultLayerInstance) defaultLayerInstance = new PredictiveLayer();
  return defaultLayerInstance;
}

export function createPredictiveLayer(config?: Partial<PredictiveLayerConfig>): PredictiveLayer {
  return new PredictiveLayer(config);
}
