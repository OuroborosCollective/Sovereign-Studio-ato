/**
 * Prediction Generator
 *
 * Top-Down prediction logic for the predictive coding layer.
 * Generates predictions based on learned patterns and existing network weights.
 *
 * @module predictive/predictionGenerator
 */

import type {
  Signal,
  Prediction,
  Synapse,
  NeuralNode,
  TraceId,
  PredictiveLayerConfig,
} from './types';

import { DEFAULT_PREDICTIVE_CONFIG } from './types';
import { LatentSpaceNavigator } from './latentSpace';

let predictionSequence = 0;

function generatePredictionId(): string {
  predictionSequence = (predictionSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `pred-${predictionSequence.toString(36).padStart(8, '0')}`;
}

export interface PredictionGeneratorOptions {
  latentSpace?: LatentSpaceNavigator;
  activationFunction?: 'identity' | 'sigmoid' | 'tanh' | 'relu';
  defaultConfidence: number;
  minSimilarityThreshold?: number;
}

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
      similarityThreshold: config.latentSpace.similarityThreshold,
    });
    this.activationFunction = this.getActivationFunction(options.activationFunction ?? 'sigmoid');
    this.defaultConfidence = options.defaultConfidence;
    this.minSimilarityThreshold = options.minSimilarityThreshold ?? config.latentSpace.similarityThreshold;
    this.config = config;
  }

  private getActivationFunction(name: 'identity' | 'sigmoid' | 'tanh' | 'relu'): (x: number) => number {
    switch (name) {
      case 'identity': return (x) => x;
      case 'sigmoid': return (x) => 1 / (1 + Math.exp(-x));
      case 'tanh': return Math.tanh;
      case 'relu': return (x) => Math.max(0, x);
      default: return (x) => 1 / (1 + Math.exp(-x));
    }
  }

  registerNode(node: NeuralNode): void {
    this.nodes.set(node.id, node);
  }

  registerSynapse(synapse: Synapse): void {
    this.synapses.set(synapse.id, synapse);
  }

  async generatePrediction(signal: Signal, traceId: TraceId): Promise<Prediction> {
    const patternMatch = await this.latentSpace.findSimilar(signal.value, signal.node);
    const networkPrediction = this.computeWeightedPrediction(signal);

    let predictedValue: number;
    let confidence: number;
    let patternId: string | undefined;
    let embedding: number[] | undefined;

    if (patternMatch && patternMatch.score >= this.minSimilarityThreshold) {
      const weight = 0.7;
      predictedValue = weight * patternMatch.pattern.signalValue + (1 - weight) * networkPrediction;
      confidence = patternMatch.score * 0.9;
      patternId = patternMatch.pattern.id;
      embedding = patternMatch.pattern.embedding;
    } else {
      predictedValue = networkPrediction;
      confidence = this.defaultConfidence;
    }

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

    this.addToHistory(signal.node, prediction);
    return prediction;
  }

  private computeWeightedPrediction(signal: Signal): number {
    const node = this.nodes.get(signal.node);
    if (!node) return signal.value;

    let weightedSum = 0;
    let totalWeight = 0;

    for (const synapse of node.incomingSynapses) {
      const sourceNode = this.nodes.get(synapse.sourceNode);
      if (!sourceNode) continue;
      weightedSum += synapse.weight * sourceNode.activation;
      totalWeight += synapse.weight;
    }

    if (totalWeight === 0) return node.previousActivation;
    return this.activationFunction(weightedSum / totalWeight);
  }

  async generateBatchPredictions(signals: Signal[], traceId: TraceId): Promise<Prediction[]> {
    return Promise.all(signals.map((signal) => this.generatePrediction(signal, traceId)));
  }

  getHistory(nodeId: string): Prediction[] {
    return this.predictionHistory.get(nodeId) ?? [];
  }

  private addToHistory(nodeId: string, prediction: Prediction): void {
    // ⚡ Bolt: Avoid redundant Map.set operations when history array already exists in map
    let history = this.predictionHistory.get(nodeId);
    if (!history) {
      history = [];
      this.predictionHistory.set(nodeId, history);
    }
    history.push(prediction);
    if (history.length > 100) history.shift();
  }

  learn(signal: Signal, prediction: Prediction, actualValue: number): void {
    // ⚡ Bolt: Consolidated single-pass embedding generation and Euclidean norm calculation.
    // Pre-allocates fixed array capacity `new Array(dim)` to eliminate dynamic array re-allocations
    // and accumulates vector sum-of-squares concurrently to eliminate a second pass over the vector.
    const { embedding, norm } = this.createEmbeddingWithNorm(signal);
    this.latentSpace.addPattern({
      id: `pattern-${signal.id}`,
      embedding,
      norm,
      signalValue: actualValue,
      node: signal.node,
      createdAt: Date.now(),
      matchCount: 0,
      avgConfidence: prediction.confidence,
    });
  }

  private createEmbeddingWithNorm(signal: Signal): { embedding: number[]; norm: number } {
    const dim = this.config.latentSpace.dimension;
    const embedding = new Array<number>(dim);
    let sumSq = 0;
    for (let i = 0; i < dim; i += 1) {
      const seed = signal.value * (i + 1) + signal.timestamp + i * 7919;
      const val = (Math.sin(seed) + 1) / 2;
      embedding[i] = val;
      sumSq += val * val;
    }
    return { embedding, norm: Math.sqrt(sumSq) };
  }

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
      for (const prediction of history) totalConfidence += prediction.confidence;
    }

    return {
      nodeCount: this.nodes.size,
      synapseCount: this.synapses.size,
      patternCount: this.latentSpace.getPatternCount(),
      avgConfidence: totalPredictions > 0 ? totalConfidence / totalPredictions : 0,
      totalPredictions,
    };
  }

  clearHistory(): void {
    this.predictionHistory.clear();
  }
}

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
