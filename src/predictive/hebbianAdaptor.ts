/**
 * Hebbian Adaptor
 *
 * Hebbian weight adaptation module for the predictive coding layer.
 * Implements synaptic weight updates using the Hebbian learning rule.
 *
 * Mathematical Foundation:
 * - Hebbian Weight Update: ΔW = η · ε(t) · ∂x̂(t)/∂W
 * - Extended: Δw_ij = η · (x_i · x_j - w_ij · x_j²)
 * - With decay: w_ij(t+1) = (1 - λ) · w_ij(t) + Δw_ij
 *
 * Features:
 * - Weight bounds clamping [0.0, 1.0]
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

// ============================================================================
// Constants
// ============================================================================

const DEFAULT_PRUNE_THRESHOLD = 0.05;
const DEFAULT_BATCH_PRUNE_INTERVAL = 1000;
const MAX_WEIGHT_BOUND = 1.0;
const MIN_WEIGHT_BOUND = 0.0;

// ============================================================================
// Hebbian Adaptor
// ============================================================================

export interface HebbianAdaptorStats {
  totalUpdates: number;
  growthEvents: number;
  decayEvents: number;
  prunedSynapses: number;
  averageWeight: number;
  maxWeight: number;
  minWeight: number;
}

/**
 * Implements Hebbian learning for synaptic weight adaptation.
 */
export class HebbianAdaptor {
  private config: HebbianConfig;
  private synapses: Map<string, Synapse> = new Map();
  private nodes: Map<string, NeuralNode> = new Map();
  private updateCount: number = 0;
  private pruneCounter: number = 0;
  private stats: HebbianAdaptorStats;

  constructor(config: Partial<HebbianConfig> = {}) {
    this.config = {
      ...DEFAULT_HEBBIAN_CONFIG,
      ...config,
    };

    this.stats = this.createEmptyStats();
  }

  /**
   * Create empty stats object.
   */
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

  /**
   * Register a synapse for learning.
   */
  registerSynapse(synapse: Synapse): void {
    this.synapses.set(synapse.id, { ...synapse });
  }

  /**
   * Register a neural node.
   */
  registerNode(node: NeuralNode): void {
    this.nodes.set(node.id, node);
  }

  /**
   * Update weight for a single synapse based on error.
   * ΔW = η · ε(t) · ∂x̂(t)/∂W
   */
  updateWeight(
    synapseId: string,
    error: PredictionError,
    previousActivation: number,
  ): WeightUpdateResult | null {
    const synapse = this.synapses.get(synapseId);
    if (!synapse) return null;

    const previousWeight = synapse.weight;

    // Compute weight change: Δw = η · error · source_activation
    // Extended Hebbian: considers both pre- and post-synaptic activity
    const preSynaptic = previousActivation;
    const postSynaptic = error.actual;

    // Hebbian term: strengthen when both are active
    const hebbianTerm = preSynaptic * postSynaptic;

    // Anti-Hebbian term: weaken when prediction is wrong
    const antiHebbianTerm = synapse.weight * postSynaptic * postSynaptic;

    // Combined update with damping
    const rawDelta = this.config.learningRate * (hebbianTerm - antiHebbianTerm);
    const dampedDelta = rawDelta * this.config.dampingFactor;

    // Apply update
    let newWeight = previousWeight + dampedDelta;

    // Apply decay
    newWeight *= this.config.decayFactor;

    // Clamp to bounds
    newWeight = this.clampWeight(newWeight);

    // Update synapse
    synapse.weight = newWeight;
    synapse.weightDelta = newWeight - previousWeight;
    synapse.lastUpdate = Date.now();
    synapse.activationCount++;

    this.updateCount++;

    // Determine event type
    let eventType: WeightUpdateResult['eventType'] = 'decay';
    if (synapse.weightDelta > 0.001) {
      eventType = 'growth';
      this.stats.growthEvents++;
    } else if (synapse.weightDelta < -0.001) {
      this.stats.decayEvents++;
    }

    // Calculate confidence based on error magnitude
    const confidence = Math.min(1, Math.abs(error.error));

    // Update stats
    this.updateStats(synapse);

    // Check if pruning is needed
    this.pruneCounter++;
    if (
      this.pruneCounter >= DEFAULT_BATCH_PRUNE_INTERVAL &&
      this.config.pruningEnabled
    ) {
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

  /**
   * Batch update weights for multiple synapses.
   */
  updateWeights(
    updates: Array<{
      synapseId: string;
      error: PredictionError;
      previousActivation: number;
    }>,
  ): WeightUpdateResult[] {
    return updates
      .map(({ synapseId, error, previousActivation }) =>
        this.updateWeight(synapseId, error, previousActivation),
      )
      .filter((result): result is WeightUpdateResult => result !== null);
  }

  /**
   * Apply Hebbian learning between co-activated nodes.
   * Called when two nodes fire together.
   */
  applyHebbianLearning(
    sourceNodeId: string,
    targetNodeId: string,
    coActivationStrength: number,
  ): WeightUpdateResult | null {
    // Find or create synapse
    let synapse = this.findSynapse(sourceNodeId, targetNodeId);

    if (!synapse) {
      // Check if we can create new connection
      if (!this.canCreateSynapse(targetNodeId)) {
        return null;
      }

      // Create new synapse
      synapse = this.createSynapse(sourceNodeId, targetNodeId, coActivationStrength);
      this.synapses.set(synapse.id, synapse);
    }

    const previousWeight = synapse.weight;

    // Hebbian update: "neurons that fire together wire together"
    // Δw = η · x_i · x_j
    const delta = this.config.learningRate * coActivationStrength;
    let newWeight = previousWeight + delta;

    // Apply decay
    newWeight *= this.config.decayFactor;

    // Clamp
    newWeight = this.clampWeight(newWeight);

    synapse.weight = newWeight;
    synapse.weightDelta = newWeight - previousWeight;
    synapse.lastUpdate = Date.now();
    synapse.activationCount++;

    this.updateCount++;

    // Update stats
    this.updateStats(synapse);

    return {
      synapseId: synapse.id,
      previousWeight,
      newWeight,
      delta: synapse.weightDelta,
      eventType: 'growth',
      confidence: coActivationStrength,
    };
  }

  /**
   * Clamp weight to valid bounds.
   */
  private clampWeight(weight: number): number {
    return Math.max(MIN_WEIGHT_BOUND, Math.min(MAX_WEIGHT_BOUND, weight));
  }

  /**
   * Find synapse between two nodes.
   */
  private findSynapse(sourceNodeId: string, targetNodeId: string): Synapse | undefined {
    for (const synapse of this.synapses.values()) {
      if (synapse.sourceNode === sourceNodeId && synapse.targetNode === targetNodeId) {
        return synapse;
      }
    }
    return undefined;
  }

  /**
   * Check if we can create a new synapse for target node.
   */
  private canCreateSynapse(targetNodeId: string): boolean {
    let incomingCount = 0;
    for (const synapse of this.synapses.values()) {
      if (synapse.targetNode === targetNodeId) {
        incomingCount++;
      }
    }
    return incomingCount < this.config.maxConnections ?? 10;
  }

  /**
   * Create a new synapse.
   */
  private createSynapse(
    sourceNodeId: string,
    targetNodeId: string,
    initialWeight: number,
  ): Synapse {
    return {
      id: `syn-${sourceNodeId}-${targetNodeId}-${Date.now().toString(36)}`,
      sourceNode: sourceNodeId,
      targetNode: targetNodeId,
      weight: this.clampWeight(initialWeight),
      lastUpdate: Date.now(),
      activationCount: 0,
      weightDelta: 0,
    };
  }

  /**
   * Prune synapses with weight below threshold.
   */
  pruneWeights(minWeight: number = DEFAULT_PRUNE_THRESHOLD): number {
    const toPrune: string[] = [];

    for (const [id, synapse] of this.synapses) {
      if (synapse.weight < minWeight) {
        toPrune.push(id);
      }
    }

    for (const id of toPrune) {
      this.synapses.delete(id);
      this.stats.prunedSynapses++;
    }

    return toPrune.length;
  }

  /**
   * Update statistics.
   */
  private updateStats(synapse: Synapse): void {
    this.stats.totalUpdates++;

    const weights = Array.from(this.synapses.values()).map((s) => s.weight);

    if (weights.length > 0) {
      this.stats.averageWeight =
        weights.reduce((sum, w) => sum + w, 0) / weights.length;
      this.stats.maxWeight = Math.max(...weights);
      this.stats.minWeight = Math.min(...weights);
    }
  }

  /**
   * Get statistics.
   */
  getStats(): HebbianAdaptorStats {
    return { ...this.stats };
  }

  /**
   * Get all synapses.
   */
  getSynapses(): Synapse[] {
    return Array.from(this.synapses.values());
  }

  /**
   * Get synapses for a node (incoming).
   */
  getIncomingSynapses(nodeId: string): Synapse[] {
    return Array.from(this.synapses.values()).filter((s) => s.targetNode === nodeId);
  }

  /**
   * Get synapses for a node (outgoing).
   */
  getOutgoingSynapses(nodeId: string): Synapse[] {
    return Array.from(this.synapses.values()).filter((s) => s.sourceNode === nodeId);
  }

  /**
   * Get synapse by ID.
   */
  getSynapse(synapseId: string): Synapse | undefined {
    return this.synapses.get(synapseId);
  }

  /**
   * Clear all synapses.
   */
  clear(): void {
    this.synapses.clear();
    this.updateCount = 0;
    this.pruneCounter = 0;
    this.stats = this.createEmptyStats();
  }

  /**
   * Set learning rate.
   */
  setLearningRate(rate: number): void {
    this.config.learningRate = Math.max(0, Math.min(1, rate));
  }

  /**
   * Get current learning rate.
   */
  getLearningRate(): number {
    return this.config.learningRate;
  }

  /**
   * Export synapses for serialization.
   */
  exportSynapses(): Synapse[] {
    return this.getSynapses();
  }

  /**
   * Import synapses from serialization.
   */
  importSynapses(synapses: Synapse[]): number {
    let imported = 0;
    for (const synapse of synapses) {
      this.synapses.set(synapse.id, { ...synapse });
      imported++;
    }
    return imported;
  }
}

// ============================================================================
// Default Factory
// ============================================================================

export function createHebbianAdaptor(
  config?: Partial<HebbianConfig>,
): HebbianAdaptor {
  return new HebbianAdaptor(config);
}

// ============================================================================
// Synaptogenesis Module (Dynamic Connection Creation)
// ============================================================================

export interface SynaptogenesisConfig {
  correlationThreshold: number;
  minSamples: number;
  maxConnectionsPerNode: number;
}

/**
 * Implements synaptogenesis: dynamically creating new synaptic connections
 * when correlated patterns are detected.
 */
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

  /**
   * Record co-activation between two nodes.
   */
  recordCoActivation(nodeA: string, nodeB: string, valueA: number, valueB: number): void {
    if (nodeA === nodeB) return;

    // Initialize buffers
    if (!this.correlationBuffer.has(nodeA)) {
      this.correlationBuffer.set(nodeA, new Map());
    }
    if (!this.correlationBuffer.get(nodeA)!.has(nodeB)) {
      this.correlationBuffer.get(nodeA)!.set(nodeB, []);
    }

    // Add to circular buffer
    const buffer = this.correlationBuffer.get(nodeA)!.get(nodeB)!;
    buffer.push(valueA * valueB);

    // Keep last minSamples
    if (buffer.length > this.config.minSamples) {
      buffer.shift();
    }
  }

  /**
   * Detect if two nodes should be connected based on correlation.
   */
  detectCorrelation(nodeA: string, nodeB: string): number {
    const buffer = this.correlationBuffer.get(nodeA)?.get(nodeB);
    if (!buffer || buffer.length < this.config.minSamples) {
      return 0;
    }

    // Calculate Pearson correlation
    const n = buffer.length;
    const sumX = buffer.reduce((s, v, i) => s + (i < n / 2 ? v : 0), 0);
    const sumY = buffer.reduce((s, v, i) => s + (i >= n / 2 ? v : 0), 0);
    const sumXY = buffer.reduce((s, v) => s + v, 0);
    const sumX2 = buffer.reduce((s, v, i) => s + (i < n / 2 ? v * v : 0), 0);
    const sumY2 = buffer.reduce((s, v, i) => s + (i >= n / 2 ? v * v : 0), 0);

    const numerator = n * sumXY - sumX * sumY;
    const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));

    if (denominator === 0) return 0;
    return numerator / denominator;
  }

  /**
   * Find candidate nodes for new connections based on correlation.
   */
  findCandidates(sourceNode: string): Array<{ node: string; correlation: number }> {
    const candidates: Array<{ node: string; correlation: number }> = [];

    const nodeCorrelations = this.correlationBuffer.get(sourceNode);
    if (!nodeCorrelations) return candidates;

    for (const [targetNode] of nodeCorrelations) {
      const correlation = this.detectCorrelation(sourceNode, targetNode);
      if (correlation >= this.config.correlationThreshold) {
        candidates.push({ node: targetNode, correlation });
      }
    }

    // Sort by correlation descending
    candidates.sort((a, b) => b.correlation - a.correlation);

    return candidates.slice(0, this.config.maxConnectionsPerNode);
  }

  /**
   * Clear correlation data.
   */
  clear(): void {
    this.correlationBuffer.clear();
  }
}
