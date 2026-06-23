/**
 * Hebbian Adaptor
 *
 * Hebbian weight adaptation module for the predictive coding layer.
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

export interface HebbianAdaptorStats {
  totalUpdates: number;
  growthEvents: number;
  decayEvents: number;
  prunedSynapses: number;
  averageWeight: number;
  maxWeight: number;
  minWeight: number;
}

export class HebbianAdaptor {
  private config: HebbianConfig;
  private synapses: Map<string, Synapse> = new Map();
  private nodes: Map<string, NeuralNode> = new Map();
  private updateCount = 0;
  private pruneCounter = 0;
  private stats: HebbianAdaptorStats;

  constructor(config: Partial<HebbianConfig> = {}) {
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
    };
  }

  registerSynapse(synapse: Synapse): void {
    this.synapses.set(synapse.id, { ...synapse });
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
    const preSynaptic = previousActivation;
    const postSynaptic = error.actual;
    const hebbianTerm = preSynaptic * postSynaptic;
    const antiHebbianTerm = synapse.weight * postSynaptic * postSynaptic;
    const rawDelta = this.config.learningRate * (hebbianTerm - antiHebbianTerm);
    const dampedDelta = rawDelta * this.config.dampingFactor;

    let newWeight = previousWeight + dampedDelta;
    newWeight *= this.config.decayFactor;
    newWeight = this.clampWeight(newWeight);

    synapse.weight = newWeight;
    synapse.weightDelta = newWeight - previousWeight;
    synapse.lastUpdate = Date.now();
    synapse.activationCount += 1;
    this.updateCount += 1;

    let eventType: WeightUpdateResult['eventType'] = 'decay';
    if (synapse.weightDelta > 0.001) {
      eventType = 'growth';
      this.stats.growthEvents += 1;
    } else if (synapse.weightDelta < -0.001) {
      this.stats.decayEvents += 1;
    }

    const confidence = Math.min(1, Math.abs(error.error));
    this.updateStats();

    this.pruneCounter += 1;
    if (this.pruneCounter >= DEFAULT_BATCH_PRUNE_INTERVAL) {
      this.pruneWeights(this.config.minWeight);
      this.pruneCounter = 0;
    }

    return {
      synapseId,
      previousWeight,
      newWeight,
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
    const delta = this.config.learningRate * coActivationStrength;
    let newWeight = previousWeight + delta;
    newWeight *= this.config.decayFactor;
    newWeight = this.clampWeight(newWeight);

    synapse.weight = newWeight;
    synapse.weightDelta = newWeight - previousWeight;
    synapse.lastUpdate = Date.now();
    synapse.activationCount += 1;
    this.updateCount += 1;
    this.updateStats();

    return {
      synapseId: synapse.id,
      previousWeight,
      newWeight,
      delta: synapse.weightDelta,
      eventType: 'growth',
      confidence: coActivationStrength,
    };
  }

  private clampWeight(weight: number): number {
    const min = this.config.weightBounds?.min ?? MIN_WEIGHT_BOUND;
    const max = this.config.weightBounds?.max ?? MAX_WEIGHT_BOUND;
    return Math.max(min, Math.min(max, weight));
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
    return incomingCount < DEFAULT_MAX_CONNECTIONS_PER_NODE;
  }

  private createSynapse(sourceNodeId: string, targetNodeId: string, initialWeight: number): Synapse {
    return {
      id: `syn-${sourceNodeId}-${targetNodeId}-${(this.updateCount + 1).toString(36)}`,
      sourceNode: sourceNodeId,
      targetNode: targetNodeId,
      weight: this.clampWeight(initialWeight),
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

    return toPrune.length;
  }

  private updateStats(): void {
    this.stats.totalUpdates += 1;
    const weights = Array.from(this.synapses.values()).map((synapse) => synapse.weight);

    if (weights.length > 0) {
      this.stats.averageWeight = weights.reduce((sum, weight) => sum + weight, 0) / weights.length;
      this.stats.maxWeight = Math.max(...weights);
      this.stats.minWeight = Math.min(...weights);
    }
  }

  getStats(): HebbianAdaptorStats {
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
    this.updateCount = 0;
    this.pruneCounter = 0;
    this.stats = this.createEmptyStats();
  }

  setLearningRate(rate: number): void {
    this.config.learningRate = Math.max(0, Math.min(1, rate));
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
    return imported;
  }
}

export function createHebbianAdaptor(config?: Partial<HebbianConfig>): HebbianAdaptor {
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
    if (denominator === 0) return 0;
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
