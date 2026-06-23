/**
 * Prediction Generator
 *
 * Top-Down prediction logic for the predictive coding layer.
 * Generates predictions based on learned patterns and existing network weights.
 *
 * Mathematical Foundation:
 * - Top-Down Prediction: x̂(t) = f(Ŵ · φ(t-1))
 * - where f is the activation function
 * - Ŵ is the weight matrix
 * - φ(t-1) is the previous layer activation
 *
 * @module predictive/predictionGenerator
 */

import type {
  Signal,
  Prediction,
  Synapse,
  NeuralNode,
  PatternEmbedding,
  TraceId,
  PredictiveLayerConfig,
  LatentSpaceSearchResult,
} from './types';

import { DEFAULT_PREDICTIVE_CONFIG } from './types';

import { LatentSpaceNavigator } from './latentSpace';

// ============================================================================
// Trace ID Counter
// ============================================================================

let predictionSequence = 0;

function generatePredictionId(): string {
  predictionSequence = (predictionSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `pred-${predictionSequence.toString(36).padStart(8, '0')}`;
}

// ============================================================================
// Prediction Generator Core
// ============================================================================

export interface PredictionGeneratorOptions {
  /** Latent space navigator for pattern matching */
  latentSpace?: LatentSpaceNavigator;
  /** Activation function to use */
  activationFunction?: 'identity' | 'sigmoid' | 'tanh' | 'relu';
  /** Default confidence for new predictions */
  defaultConfidence: number;
  /** Minimum similarity threshold for pattern matching */
  minSimilarityThreshold: number;
}

/**
 * Generates Top-Down predictions for runtime signals.
 * Uses weighted network connections and latent space patterns.
 */
export class PredictionGenerator {
  private latentSpace: LatentSpaceNavigator;
  private nodes: Map<string, NeuralNode> = new Map();
  private synapses: Map<string, Synapse> = new Map();
  private predictionHistory: Map<string, Prediction[]> = new Map();
  private activationFunction: (x: number) => number;
  private defaultConfidence: number;
  private minSimilarityThreshold: number;
  private config: PredictiveLayerConfig;

  constructor(
    options: PredictionGeneratorOptions = { defaultConfidence: 0.5 },
    config: PredictiveLayerConfig = DEFAULT_PREDICTIVE_CONFIG,
  ) {
    this.latentSpace = options.latentSpace ?? new LatentSpaceNavigator({
      dimension: config.latentSpace.dimension,
      maxPatterns: config.latentSpace.maxPatterns,
    });
    this.activationFunction = this.getActivationFunction(options.activationFunction ?? 'sigmoid');
    this.defaultConfidence = options.defaultConfidence;
    this.minSimilarityThreshold = config.latentSpace.similarityThreshold;
    this.config = config;
  }

  /**
   * Get activation function by name.
   */
  private getActivationFunction(name: 'identity' | 'sigmoid' | 'tanh' | 'relu'): (x: number) => number {
    switch (name) {
      case 'identity':
        return (x) => x;
      case 'sigmoid':
        return (x) => 1 / (1 + Math.exp(-x));
      case 'tanh':
        return Math.tanh;
      case 'relu':
        return (x) => Math.max(0, x);
      default:
        return (x) => 1 / (1 + Math.exp(-x));
    }
  }

  /**
   * Register a neural node for prediction.
   */
  registerNode(node: NeuralNode): void {
    this.nodes.set(node.id, node);
  }

  /**
   * Register a synapse for weighted prediction.
   */
  registerSynapse(synapse: Synapse): void {
    this.synapses.set(synapse.id, synapse);
  }

  /**
   * Generate a prediction for a signal.
   * Combines weighted network prediction with latent space pattern matching.
   */
  async generatePrediction(
    signal: Signal,
    traceId: TraceId,
  ): Promise<Prediction> {
    const startTime = performance.now();

    // Try latent space pattern matching first
    const patternMatch = await this.latentSpace.findSimilar(signal.value, signal.node);

    // Calculate weighted prediction from network
    const networkPrediction = this.computeWeightedPrediction(signal);

    // Combine predictions
    let predictedValue: number;
    let confidence: number;
    let patternId: string | undefined;
    let embedding: number[] | undefined;

    if (patternMatch && patternMatch.score >= this.minSimilarityThreshold) {
      // Use latent space prediction
      const weight = 0.7;
      predictedValue = weight * patternMatch.pattern.signalValue + (1 - weight) * networkPrediction;
      confidence = patternMatch.score * 0.9; // Scale confidence by pattern match
      patternId = patternMatch.pattern.id;
      embedding = patternMatch.pattern.embedding;
    } else {
      // Fall back to network prediction or default
      predictedValue = networkPrediction;
      confidence = this.defaultConfidence;
    }

    // Apply temporal smoothing if we have history
    const history = this.predictionHistory.get(signal.node);
    if (history && history.length > 0) {
      const lastPrediction = history[history.length - 1];
      predictedValue = 0.7 * predictedValue + 0.3 * lastPrediction.predictedValue;
    }

    const prediction: Prediction = {
      id: generatePredictionId(),
      predictedValue,
      confidence: Math.max(0, Math.min(1, confidence)),
      node: signal.node,
      timestamp: Date.now(),
      traceId,
      patternId,
      embedding,
    };

    // Store in history
    this.addToHistory(signal.node, prediction);

    return prediction;
  }

  /**
   * Compute prediction from weighted network connections.
   * x̂(t) = f(Σ(w_i · x_i))
   */
  private computeWeightedPrediction(signal: Signal): number {
    const node = this.nodes.get(signal.node);
    if (!node) {
      return signal.value; // Fallback: predict actual value
    }

    // Sum weighted inputs from incoming synapses
    let weightedSum = 0;
    let totalWeight = 0;

    for (const synapse of node.incomingSynapses) {
      const sourceNode = this.nodes.get(synapse.sourceNode);
      if (sourceNode) {
        weightedSum += synapse.weight * sourceNode.activation;
        totalWeight += synapse.weight;
      }
    }

    // If no connections, use previous activation
    if (totalWeight === 0) {
      return node.previousActivation;
    }

    // Normalize and apply activation
    const normalizedInput = totalWeight > 0 ? weightedSum / totalWeight : 0;
    return this.activationFunction(normalizedInput);
  }

  /**
   * Generate batch predictions for multiple signals.
   */
  async generateBatchPredictions(
    signals: Signal[],
    traceId: TraceId,
  ): Promise<Prediction[]> {
    return Promise.all(signals.map((signal) => this.generatePrediction(signal, traceId)));
  }

  /**
   * Get prediction history for a node.
   */
  getHistory(nodeId: string): Prediction[] {
    return this.predictionHistory.get(nodeId) ?? [];
  }

  /**
   * Add prediction to history with size limit.
   */
  private addToHistory(nodeId: string, prediction: Prediction): void {
    const history = this.predictionHistory.get(nodeId) ?? [];
    history.push(prediction);

    // Keep last 100 predictions per node
    if (history.length > 100) {
      history.shift();
    }

    this.predictionHistory.set(nodeId, history);
  }

  /**
   * Learn from a signal-prediction pair.
   * Updates latent space with the observed pattern.
   */
  learn(signal: Signal, prediction: Prediction, actualValue: number): void {
    // Create embedding from signal features
    const embedding = this.createEmbedding(signal, prediction);

    // Add to latent space
    this.latentSpace.addPattern({
      id: `pattern-${signal.id}`,
      embedding,
      norm: this.computeNorm(embedding),
      signalValue: actualValue,
      node: signal.node,
      createdAt: Date.now(),
      matchCount: 0,
      avgConfidence: prediction.confidence,
    });
  }

  /**
   * Create embedding vector from signal features.
   */
  private createEmbedding(signal: Signal, prediction: Prediction): number[] {
    const dim = this.config.latentSpace.dimension;
    const embedding: number[] = [];

    // Create a simple embedding based on signal properties
    // In a full implementation, this would use a learned encoder
    for (let i = 0; i < dim; i++) {
      // Deterministic pseudo-random based on signal properties
      const seed = signal.value * (i + 1) + signal.timestamp + i * 7919;
      embedding.push((Math.sin(seed) + 1) / 2); // Normalize to [0, 1]
    }

    return embedding;
  }

  /**
   * Compute L2 norm of a vector.
   */
  private computeNorm(vector: number[]): number {
    return Math.sqrt(vector.reduce((sum, v) => sum + v * v, 0));
  }

  /**
   * Get statistics about predictions.
   */
  getStats(): {
    nodeCount: number;
    synapseCount: number;
    patternCount: number;
    avgConfidence: number;
    totalPredictions: number;
  } {
    let totalConfidence = 0;
    let totalPredictions = 0;

    for (const history of this.predictionHistory.values()) {
      totalPredictions += history.length;
      for (const pred of history) {
        totalConfidence += pred.confidence;
      }
    }

    return {
      nodeCount: this.nodes.size,
      synapseCount: this.synapses.size,
      patternCount: this.latentSpace.getPatternCount(),
      avgConfidence: totalPredictions > 0 ? totalConfidence / totalPredictions : 0,
      totalPredictions,
    };
  }

  /**
   * Clear all prediction history.
   */
  clearHistory(): void {
    this.predictionHistory.clear();
  }
}

// ============================================================================
// Default Factory
// ============================================================================

export function createPredictionGenerator(
  options?: Partial<PredictionGeneratorOptions>,
  config?: PredictiveLayerConfig,
): PredictionGenerator {
  return new PredictionGenerator(
    {
      defaultConfidence: 0.5,
      minSimilarityThreshold: config?.latentSpace.similarityThreshold ?? 0.7,
      ...options,
    },
    config ?? DEFAULT_PREDICTIVE_CONFIG,
  );
}
