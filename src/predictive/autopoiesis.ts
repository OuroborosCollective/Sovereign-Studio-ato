/**
 * Autopoiesis Engine
 *
 * Implements dynamic synaptic topology changes:
 * - Synaptogenesis: Creates new connections when correlated patterns occur
 * - Synaptic Pruning: Removes weak connections to optimize the network
 *
 * Based on the biological principle of autopoiesis (self-creating):
 * The network dynamically adapts its topology based on observed patterns.
 *
 * @module predictive/autopoiesis
 */

import type { Synapse, NeuralNode, Signal, PredictionError } from './types';

// ============================================================================
// Types
// ============================================================================

export interface AutopoiesisConfig {
  /** Enable synaptogenesis (new connection creation) */
  synaptogenesisEnabled: boolean;
  /** Enable synaptic pruning */
  pruningEnabled: boolean;
  /** Correlation threshold for creating new connections */
  correlationThreshold: number;
  /** Minimum weight for pruning */
  minWeight: number;
  /** Maximum connections per node */
  maxConnectionsPerNode: number;
  /** Minimum samples before correlation is valid */
  minCorrelationSamples: number;
  /** Prune interval (in updates) */
  pruneInterval: number;
  /** Initial weight for new synapses */
  initialWeight: number;
}

export interface SynapseCandidate {
  sourceNode: string;
  targetNode: string;
  correlation: number;
  weight: number;
}

export interface AutopoiesisStats {
  synaptogenesisEvents: number;
  pruningEvents: number;
  totalCorrelationsTracked: number;
  activeConnections: number;
  prunedConnections: number;
}

// ============================================================================
// Default Configuration
// ============================================================================

export const DEFAULT_AUTOPOIESIS_CONFIG: AutopoiesisConfig = {
  synaptogenesisEnabled: true,
  pruningEnabled: true,
  correlationThreshold: 0.7,
  minWeight: 0.05,
  maxConnectionsPerNode: 10,
  minCorrelationSamples: 100,
  pruneInterval: 1000,
  initialWeight: 0.3,
};

// ============================================================================
// Autopoiesis Engine
// ============================================================================

/**
 * Manages dynamic network topology through synaptogenesis and pruning.
 */
export class AutopoiesisEngine {
  private config: AutopoiesisConfig;
  private correlationMatrix: Map<string, Map<string, number[]>> = new Map();
  private coActivationCounts: Map<string, Map<string, number>> = new Map();
  private updateCount: number = 0;
  private stats: AutopoiesisStats;

  constructor(config: Partial<AutopoiesisConfig> = {}) {
    this.config = { ...DEFAULT_AUTOPOIESIS_CONFIG, ...config };
    this.stats = {
      synaptogenesisEvents: 0,
      pruningEvents: 0,
      totalCorrelationsTracked: 0,
      activeConnections: 0,
      prunedConnections: 0,
    };
  }

  /**
   * Record co-activation between two nodes.
   * This builds the correlation data for synaptogenesis.
   */
  recordCoActivation(signal: Signal, otherSignal?: Signal): void {
    if (!otherSignal) return;
    if (signal.node === otherSignal.node) return;

    const key = this.getKey(signal.node, otherSignal.node);
    
    // Initialize if needed
    if (!this.correlationMatrix.has(key)) {
      this.correlationMatrix.set(key, new Map());
    }
    
    const matrix = this.correlationMatrix.get(key)!;
    
    // Store value pairs for correlation calculation
    if (!matrix.has(signal.node)) {
      matrix.set(signal.node, []);
    }
    matrix.get(signal.node)!.push(signal.value);
    
    if (!matrix.has(otherSignal.node)) {
      matrix.set(otherSignal.node, []);
    }
    matrix.get(otherSignal.node)!.push(otherSignal.value);
    
    // Track co-activation count
    this.incrementCoActivation(signal.node, otherSignal.node);
    
    this.stats.totalCorrelationsTracked++;
  }

  /**
   * Record correlation data from prediction errors.
   */
  recordErrorCorrelation(error: PredictionError, relatedSignal?: Signal): void {
    if (!relatedSignal) return;
    this.recordCoActivation(
      { id: '', node: error.node, value: error.error, timestamp: error.timestamp, traceId: error.traceId },
      relatedSignal,
    );
  }

  /**
   * Increment co-activation count between two nodes.
   */
  private incrementCoActivation(nodeA: string, nodeB: string): void {
    if (!this.coActivationCounts.has(nodeA)) {
      this.coActivationCounts.set(nodeA, new Map());
    }
    const counts = this.coActivationCounts.get(nodeA)!;
    counts.set(nodeB, (counts.get(nodeB) ?? 0) + 1);
  }

  /**
   * Get correlation key for two nodes.
   */
  private getKey(nodeA: string, nodeB: string): string {
    return nodeA < nodeB ? `${nodeA}::${nodeB}` : `${nodeB}::${nodeA}`;
  }

  /**
   * Calculate Pearson correlation coefficient between two node values.
   */
  calculateCorrelation(nodeA: string, nodeB: string): number {
    const key = this.getKey(nodeA, nodeB);
    const matrix = this.correlationMatrix.get(key);
    
    if (!matrix) return 0;
    
    const valuesA = matrix.get(nodeA);
    const valuesB = matrix.get(nodeB);
    
    if (!valuesA || !valuesB || valuesA.length < this.config.minCorrelationSamples) {
      return 0;
    }

    // Use minimum length
    const n = Math.min(valuesA.length, valuesB.length);
    
    // Calculate means
    let sumA = 0, sumB = 0;
    for (let i = 0; i < n; i++) {
      sumA += valuesA[i];
      sumB += valuesB[i];
    }
    const meanA = sumA / n;
    const meanB = sumB / n;

    // Calculate correlation
    let numerator = 0;
    let denomA = 0;
    let denomB = 0;
    
    for (let i = 0; i < n; i++) {
      const diffA = valuesA[i] - meanA;
      const diffB = valuesB[i] - meanB;
      numerator += diffA * diffB;
      denomA += diffA * diffA;
      denomB += diffB * diffB;
    }

    const denominator = Math.sqrt(denomA * denomB);
    if (denominator === 0) return 0;

    return numerator / denominator;
  }

  /**
   * Find candidate synapses to create based on correlation patterns.
   */
  findSynaptogenesisCandidates(existingSynapses: Synapse[]): SynapseCandidate[] {
    if (!this.config.synaptogenesisEnabled) return [];

    const candidates: SynapseCandidate[] = [];
    const existingTargets = new Set<string>();
    const existingSources = new Set<string>();

    // Track existing connections
    for (const synapse of existingSynapses) {
      existingTargets.add(synapse.targetNode);
      existingSources.add(synapse.sourceNode);
    }

    // Check all tracked correlations
    for (const [key] of this.correlationMatrix) {
      const [nodeA, nodeB] = key.split('::');
      
      const correlation = this.calculateCorrelation(nodeA, nodeB);
      
      if (correlation >= this.config.correlationThreshold) {
        // Check if connection doesn't exist
        const hasForwardConnection = existingSynapses.some(
          s => s.sourceNode === nodeA && s.targetNode === nodeB
        );
        const hasReverseConnection = existingSynapses.some(
          s => s.sourceNode === nodeB && s.targetNode === nodeA
        );

        if (!hasForwardConnection && !hasReverseConnection) {
          // Determine direction based on co-activation counts
          const forwardCount = this.coActivationCounts.get(nodeA)?.get(nodeB) ?? 0;
          const reverseCount = this.coActivationCounts.get(nodeB)?.get(nodeA) ?? 0;

          const [source, target] = forwardCount >= reverseCount ? [nodeA, nodeB] : [nodeB, nodeA];
          const targetConnections = existingSynapses.filter(s => s.targetNode === target).length;

          if (targetConnections < this.config.maxConnectionsPerNode) {
            candidates.push({
              sourceNode: source,
              targetNode: target,
              correlation,
              weight: this.config.initialWeight * correlation,
            });
          }
        }
      }
    }

    // Sort by correlation descending
    candidates.sort((a, b) => b.correlation - a.correlation);

    return candidates;
  }

  /**
   * Get synapses to prune based on weight threshold.
   */
  findPruningCandidates(synapses: Synapse[]): string[] {
    if (!this.config.pruningEnabled) return [];

    return synapses
      .filter(s => s.weight < this.config.minWeight)
      .map(s => s.id);
  }

  /**
   * Run pruning pass on the network.
   * Returns IDs of pruned synapses.
   */
  runPruningPass(synapses: Synapse[]): string[] {
    this.updateCount++;
    
    if (this.updateCount % this.config.pruneInterval !== 0) {
      return [];
    }

    const toPrune = this.findPruningCandidates(synapses);
    
    for (const id of toPrune) {
      this.stats.pruningEvents++;
      this.stats.prunedConnections++;
    }

    return toPrune;
  }

  /**
   * Get statistics.
   */
  getStats(): AutopoiesisStats {
    return { ...this.stats };
  }

  /**
   * Reset all correlation data.
   */
  reset(): void {
    this.correlationMatrix.clear();
    this.coActivationCounts.clear();
    this.updateCount = 0;
    this.stats = {
      synaptogenesisEvents: 0,
      pruningEvents: 0,
      totalCorrelationsTracked: 0,
      activeConnections: this.stats.activeConnections,
      prunedConnections: this.stats.prunedConnections,
    };
  }

  /**
   * Update configuration.
   */
  updateConfig(config: Partial<AutopoiesisConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * Export correlation matrix for persistence.
   */
  exportCorrelationMatrix(): Record<string, { nodeA: string; nodeB: string; correlation: number }[]> {
    const result: Record<string, { nodeA: string; nodeB: string; correlation: number }[]> = {};

    for (const [key] of this.correlationMatrix) {
      const [nodeA, nodeB] = key.split('::');
      const correlation = this.calculateCorrelation(nodeA, nodeB);
      
      if (correlation !== 0) {
        if (!result.correlations) result.correlations = [];
        result.correlations.push({ nodeA, nodeB, correlation });
      }
    }

    return result;
  }
}

// ============================================================================
// Integration Helper
// ============================================================================

/**
 * Integrate autopoiesis engine with existing synapses.
 */
export function integrateAutopoiesis(
  engine: AutopoiesisEngine,
  existingSynapses: Synapse[],
  existingNodes: NeuralNode[],
): {
  newSynapses: SynapseCandidate[];
  pruneIds: string[];
} {
  // Find new synapse candidates
  const newCandidates = engine.findSynaptogenesisCandidates(existingSynapses);
  
  // Run pruning pass
  const pruneIds = engine.runPruningPass(existingSynapses);

  return {
    newSynapses: newCandidates,
    pruneIds,
  };
}
