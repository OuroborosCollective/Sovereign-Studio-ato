/**
 * Hebbian Adaptor
 *
 * Hebbian weight adaptation module for the predictive coding layer.
 * Implements synaptic weight updates using the Hebbian learning rule.
 *
 * Mathematical Foundation:
 * - Error-driven Hebbian update: ΔW = η · ε(t) · ∂x̂(t)/∂W
 * - Extended stabilizing update: Δw_ij = η · (x_i · x_j - w_ij · x_j²)
 * - Decay-bounded state: w_ij(t+1) = (1 - λ) · (w_ij(t) + Δw_ij), with λ = 1 - decayFactor
 *
 * Runtime interpretation:
 * - x_i is the previous/source activation.
 * - x_j is the current target/actual activation.
 * - ε(t) is the signed prediction error.
 * - ∂x̂(t)/∂W is approximated by the source activation for linear local prediction.
 * - Every update is clamped to configured bounds and recorded as growth/decay.
 *
 * Features:
 * - Weight bounds clamping [0.0, 1.0] by default
 * - Damping factor to prevent oscillation
 * - Synaptic pruning for weak connections
 * - Batch pruning for efficiency
 *
 * @module predictive/hebbianAdaptor
 */

import type {
  Synapse,
  PredictionError,
  WeightUpdateResult,
  HebbianConfig,
  NeuralNode,
} from './types';

import { DEFAULT_HEBBIAN_CONFIG } from './types';

const DEFAULT_PRUNE_THRESHOLD = 0.05;
const DEFAULT_BATCH_PRUNE_INTERVAL = 1000;
const MAX_WEIGHT_BOUND = 1.0;
const MIN_WEIGHT_BOUND = 0.0;
const DEFAULT_MAX_CONNECTIONS_PER_NODE = 10;
const WEIGHT_EPSILON = 0.001;
const CORRELATION_EPSILON = 1e-9;
const COACTIVATION_NOISE_THRESHOLD = 0.1;

type HebbianRuntimeConfig = HebbianConfig & { maxConnections?: number };

export interface HebbianAdaptorStats {
  totalUpdates: number;
  growthEvents: number;
  decayEvents: number;
  prunedSynapses: number;
  averageWeight: number;
  maxWeight: number;
  minWeight: number;
  synapseCount: number;
}

export interface HebbianMathTrace {
  preSynaptic: number;
  postSynaptic: number;
  predictionError: number;
  predictionGradient: number;
  errorDrivenDelta: number;
  extendedDelta: number;
  blendedDelta: number;
  dampedDelta: number;
  decayedWeight: number;
  clampedWeight: number;
}

function finiteOr(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function configuredMin(config: HebbianRuntimeConfig): number {
  return finiteOr(config.weightBounds?.min, MIN_WEIGHT_BOUND);
}

function configuredMax(config: HebbianRuntimeConfig): number {
  return finiteOr(config.weightBounds?.max, config.maxWeight ?? MAX_WEIGHT_BOUND);
}

export function calculatePredictionGradient(preSynaptic: number): number {
  return finiteOr(preSynaptic);
}

export function calculateErrorDrivenDelta(config: HebbianRuntimeConfig, predictionError: number, predictionGradient: number): number {
  return finiteOr(config.learningRate) * finiteOr(predictionError) * finiteOr(predictionGradient);
}

export function calculateExtendedHebbianDelta(
  config: HebbianRuntimeConfig,
  currentWeight: number,
  preSynaptic: number,
  postSynaptic: number,
): number {
  const xI = finiteOr(preSynaptic);
  const xJ = finiteOr(postSynaptic);
  const wIJ = finiteOr(currentWeight);
  return finiteOr(config.learningRate) * ((xI * xJ) - (wIJ * xJ * xJ));
}

export function applyHebbianDamping(config: HebbianRuntimeConfig, delta: number): number {
  return finiteOr(delta) * finiteOr(config.dampingFactor, 1);
}

export function applyHebbianDecay(currentWeight: number, delta: number, config: HebbianRuntimeConfig): number {
  return (finiteOr(currentWeight) + finiteOr(delta)) * finiteOr(config.decayFactor, 1);
}

export function calculateHebbianMathTrace(
  config: HebbianRuntimeConfig,
  currentWeight: number,
  error: PredictionError,
  previousActivation: number,
): HebbianMathTrace {
  const preSynaptic = finiteOr(previousActivation);
  const postSynaptic = finiteOr(error.actual);
  const predictionError = finiteOr(error.error);
  const predictionGradient = calculatePredictionGradient(preSynaptic);
  const errorDrivenDelta = calculateErrorDrivenDelta(config, predictionError, predictionGradient);
  const extendedDelta = calculateExtendedHebbianDelta(config, currentWeight, preSynaptic, postSynaptic);
  const blendedDelta = (errorDrivenDelta + extendedDelta) / 2;
  const dampedDelta = applyHebbianDamping(config, blendedDelta);
  const decayedWeight = applyHebbianDecay(currentWeight, dampedDelta, config);
  const clampedWeight = clamp(decayedWeight, configuredMin(config), configuredMax(config));

  return {
    preSynaptic,
    postSynaptic,
    predictionError,
    predictionGradient,
    errorDrivenDelta,
    extendedDelta,
    blendedDelta,
    dampedDelta,
    decayedWeight,
    clampedWeight,
  };
}

export function calculateCoActivationDelta(config: HebbianRuntimeConfig, coActivationStrength: number): number {
  return finiteOr(config.learningRate) * finiteOr(coActivationStrength);
}

function classifyWeightEvent(delta: number): WeightUpdateResult['eventType'] {
  if (delta > WEIGHT_EPSILON) return 'growth';
  return 'decay';
}

export class HebbianAdaptor {
  private config: HebbianRuntimeConfig;
  private synapses: Map<string, Synapse> = new Map();
  private nodes: Map<string, NeuralNode> = new Map();
  private updateCount = 0;
  private pruneCounter = 0;
  private stats: HebbianAdaptorStats;
  private lastTrace: HebbianMathTrace | null = null;

  constructor(config: Partial<HebbianRuntimeConfig> = {}) {
    this.config = { ...DEFAULT_HEBBIAN_CONFIG, ...config };
    this.stats = this.createEmptyStats();
  }

  private createEmptyStats(): HebbianAdaptorStats {
    return {
      totalUpdates: 0,
      growthEvents: 0,
      decayEvents: 0,
      prunedSynapses: 0,
      averageWeight: 0,
      maxWeight: 0,
      minWeight: 1,
      synapseCount: 0,
    };
  }

  registerSynapse(synapse: Synapse): void {
    this.synapses.set(synapse.id, { ...synapse });
    this.updateStats(false);
  }

  registerNode(node: NeuralNode): void {
    this.nodes.set(node.id, node);
  }

  updateWeight(
    synapseId: string,
    error: PredictionError,
    previousActivation: number,
  ): WeightUpdateResult | null {
    const synapse = this.synapses.get(synapseId);
    if (!synapse) return null;

    const previousWeight = synapse.weight;
    const trace = calculateHebbianMathTrace(this.config, previousWeight, error, previousActivation);
    this.lastTrace = trace;

    synapse.weight = trace.clampedWeight;
    synapse.weightDelta = trace.clampedWeight - previousWeight;
    synapse.lastUpdate = Date.now();
    synapse.activationCount += 1;
    this.updateCount += 1;

    const eventType = classifyWeightEvent(synapse.weightDelta);
    if (eventType === 'growth') this.stats.growthEvents += 1;
    else this.stats.decayEvents += 1;

    const confidence = clamp(Math.abs(finiteOr(error.error)), 0, 1);
    this.updateStats();

    this.pruneCounter += 1;
    if (this.pruneCounter >= DEFAULT_BATCH_PRUNE_INTERVAL) {
      this.pruneWeights(this.config.minWeight);
      this.pruneCounter = 0;
    }

    return {
      synapseId,
      previousWeight,
      newWeight: synapse.weight,
      delta: synapse.weightDelta,
      eventType,
      confidence,
    };
  }

  updateWeights(updates: Array<{ synapseId: string; error: PredictionError; previousActivation: number }>): WeightUpdateResult[] {
    return updates
      .map(({ synapseId, error, previousActivation }) => this.updateWeight(synapseId, error, previousActivation))
      .filter((result): result is WeightUpdateResult => result !== null);
  }

  applyHebbianLearning(sourceNodeId: string, targetNodeId: string, coActivationStrength: number): WeightUpdateResult | null {
    let synapse = this.findSynapse(sourceNodeId, targetNodeId);

    if (!synapse) {
      if (!this.canCreateSynapse(targetNodeId)) return null;
      synapse = this.createSynapse(sourceNodeId, targetNodeId, coActivationStrength);
      this.synapses.set(synapse.id, synapse);
    }

    const previousWeight = synapse.weight;
    const delta = applyHebbianDamping(this.config, calculateCoActivationDelta(this.config, coActivationStrength));
    const decayedWeight = applyHebbianDecay(previousWeight, delta, this.config);
    const newWeight = clamp(decayedWeight, configuredMin(this.config), configuredMax(this.config));

    synapse.weight = newWeight;
    synapse.weightDelta = newWeight - previousWeight;
    synapse.lastUpdate = Date.now();
    synapse.activationCount += 1;
    this.updateCount += 1;

    const eventType = classifyWeightEvent(synapse.weightDelta);
    if (eventType === 'growth') this.stats.growthEvents += 1;
    else this.stats.decayEvents += 1;

    this.updateStats();

    return {
      synapseId: synapse.id,
      previousWeight,
      newWeight,
      delta: synapse.weightDelta,
      eventType,
      confidence: clamp(coActivationStrength, 0, 1),
    };
  }

  getLastMathTrace(): HebbianMathTrace | null {
    return this.lastTrace ? { ...this.lastTrace } : null;
  }

  private findSynapse(sourceNodeId: string, targetNodeId: string): Synapse | undefined {
    for (const synapse of this.synapses.values()) {
      if (synapse.sourceNode === sourceNodeId && synapse.targetNode === targetNodeId) return synapse;
    }
    return undefined;
  }

  private canCreateSynapse(targetNodeId: string): boolean {
    let incomingCount = 0;
    for (const synapse of this.synapses.values()) {
      if (synapse.targetNode === targetNodeId) incomingCount += 1;
    }
    return incomingCount < (this.config.maxConnections ?? DEFAULT_MAX_CONNECTIONS_PER_NODE);
  }

  private createSynapse(sourceNodeId: string, targetNodeId: string, initialWeight: number): Synapse {
    return {
      id: `syn-${sourceNodeId}-${targetNodeId}-${(this.updateCount + 1).toString(36)}`,
      sourceNode: sourceNodeId,
      targetNode: targetNodeId,
      weight: clamp(initialWeight, configuredMin(this.config), configuredMax(this.config)),
      lastUpdate: Date.now(),
      activationCount: 0,
      weightDelta: 0,
    };
  }

  pruneWeights(minWeight: number = DEFAULT_PRUNE_THRESHOLD): number {
    const toPrune: string[] = [];
    for (const [id, synapse] of this.synapses) {
      if (synapse.weight < minWeight) toPrune.push(id);
    }

    for (const id of toPrune) {
      this.synapses.delete(id);
      this.stats.prunedSynapses += 1;
    }

    this.updateStats(false);
    return toPrune.length;
  }

  private updateStats(countUpdate = true): void {
    if (countUpdate) this.stats.totalUpdates += 1;
    const weights = Array.from(this.synapses.values()).map((synapse) => synapse.weight);
    this.stats.synapseCount = weights.length;

    if (weights.length > 0) {
      this.stats.averageWeight = weights.reduce((sum, weight) => sum + weight, 0) / weights.length;
      this.stats.maxWeight = Math.max(...weights);
      this.stats.minWeight = Math.min(...weights);
    } else {
      this.stats.averageWeight = 0;
      this.stats.maxWeight = 0;
      this.stats.minWeight = 1;
    }
  }

  getStats(): HebbianAdaptorStats {
    this.updateStats(false);
    return { ...this.stats };
  }

  getSynapses(): Synapse[] {
    return Array.from(this.synapses.values());
  }

  getIncomingSynapses(nodeId: string): Synapse[] {
    return Array.from(this.synapses.values()).filter((synapse) => synapse.targetNode === nodeId);
  }

  getOutgoingSynapses(nodeId: string): Synapse[] {
    return Array.from(this.synapses.values()).filter((synapse) => synapse.sourceNode === nodeId);
  }

  getSynapse(synapseId: string): Synapse | undefined {
    return this.synapses.get(synapseId);
  }

  clear(): void {
    this.synapses.clear();
    this.nodes.clear();
    this.updateCount = 0;
    this.pruneCounter = 0;
    this.lastTrace = null;
    this.stats = this.createEmptyStats();
  }

  setLearningRate(rate: number): void {
    this.config.learningRate = clamp(rate, 0, 1);
  }

  getLearningRate(): number {
    return this.config.learningRate;
  }

  exportSynapses(): Synapse[] {
    return this.getSynapses();
  }

  importSynapses(synapses: Synapse[]): number {
    let imported = 0;
    for (const synapse of synapses) {
      this.synapses.set(synapse.id, { ...synapse });
      imported += 1;
    }
    this.updateStats(false);
    return imported;
  }
}

export function createHebbianAdaptor(config?: Partial<HebbianRuntimeConfig>): HebbianAdaptor {
  return new HebbianAdaptor(config);
}

export interface SynaptogenesisConfig {
  correlationThreshold: number;
  minSamples: number;
  maxConnectionsPerNode: number;
}

export class Synaptogenesis {
  private config: SynaptogenesisConfig;
  private correlationBuffer: Map<string, Map<string, number[]>> = new Map();

  constructor(config: Partial<SynaptogenesisConfig> = {}) {
    this.config = {
      correlationThreshold: 0.7,
      minSamples: 100,
      maxConnectionsPerNode: 10,
      ...config,
    };
  }

  recordCoActivation(nodeA: string, nodeB: string, valueA: number, valueB: number): void {
    if (nodeA === nodeB) return;
    if (!this.correlationBuffer.has(nodeA)) this.correlationBuffer.set(nodeA, new Map());
    if (!this.correlationBuffer.get(nodeA)?.has(nodeB)) this.correlationBuffer.get(nodeA)?.set(nodeB, []);

    const buffer = this.correlationBuffer.get(nodeA)?.get(nodeB);
    if (!buffer) return;
    buffer.push(valueA * valueB);
    if (buffer.length > this.config.minSamples) buffer.shift();
  }

  detectCorrelation(nodeA: string, nodeB: string): number {
    const buffer = this.correlationBuffer.get(nodeA)?.get(nodeB);
    if (!buffer || buffer.length < this.config.minSamples) return 0;

    const midpoint = Math.floor(buffer.length / 2);
    const x = buffer.slice(0, midpoint);
    const y = buffer.slice(midpoint, midpoint + x.length);
    if (!x.length || x.length !== y.length) return 0;

    const n = x.length;
    const sumX = x.reduce((sum, value) => sum + value, 0);
    const sumY = y.reduce((sum, value) => sum + value, 0);
    const sumXY = x.reduce((sum, value, index) => sum + value * y[index], 0);
    const sumX2 = x.reduce((sum, value) => sum + value * value, 0);
    const sumY2 = y.reduce((sum, value) => sum + value * value, 0);
    const numerator = n * sumXY - sumX * sumY;
    const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
    if (Math.abs(denominator) < CORRELATION_EPSILON) {
      const averageCoActivation = buffer.reduce((sum, value) => sum + value, 0) / buffer.length;
      if (averageCoActivation > COACTIVATION_NOISE_THRESHOLD) return 1;
      if (averageCoActivation < -COACTIVATION_NOISE_THRESHOLD) return -1;
      return 0;
    }
    return numerator / denominator;
  }

  findCandidates(sourceNode: string): Array<{ node: string; correlation: number }> {
    const candidates: Array<{ node: string; correlation: number }> = [];
    const nodeCorrelations = this.correlationBuffer.get(sourceNode);
    if (!nodeCorrelations) return candidates;

    for (const [targetNode] of nodeCorrelations) {
      const correlation = this.detectCorrelation(sourceNode, targetNode);
      if (correlation >= this.config.correlationThreshold) candidates.push({ node: targetNode, correlation });
    }

    candidates.sort((a, b) => b.correlation - a.correlation || a.node.localeCompare(b.node));
    return candidates.slice(0, this.config.maxConnectionsPerNode);
  }

  clear(): void {
    this.correlationBuffer.clear();
  }
}
