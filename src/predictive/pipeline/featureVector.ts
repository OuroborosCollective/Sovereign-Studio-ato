/**
 * Feature Vector Pipeline
 *
 * Deterministic feature vector generation from signal windows.
 * Feature vectors are used for ML inference lanes (ScaNN, Wolfram).
 *
 * @module predictive/pipeline/featureVector
 */

import type { TickWindow, TickWindowReceipt } from './tickWindow';
import { extractTick, extractSequence } from './tickWindow';

// ============================================================================
// Types
// ============================================================================

export interface FeatureVector {
  id: string;
  windowId: string;
  dimensions: Record<string, number>;
  receipt: FeatureVectorReceipt;
}

export interface FeatureVectorReceipt {
  vectorId: string;
  windowReceipt: TickWindowReceipt;
  dimensions: string[];
  featureHash: string;
  timestamp: number;
}

export interface FeatureVectorConfig {
  includeTickStats: boolean;
  includeSequenceStats: boolean;
  includeNodeDistribution: boolean;
  includeValueStats: boolean;
}

// ============================================================================
// Internal Hashing
// ============================================================================

function hashFeatureVector(dimensions: Record<string, number>): string {
  const entries = Object.entries(dimensions)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}:${v.toFixed(4)}`);

  return polynomialRollingHash(entries.join('|'));
}

function polynomialRollingHash(str: string): string {
  const PRIME = 31;
  const MOD = 1_000_000_007;

  let hash = 0;
  let power = 1;

  for (let i = 0; i < str.length; i++) {
    const charCode = str.charCodeAt(i);
    hash = (hash + (charCode * power) % MOD) % MOD;
    power = (power * PRIME) % MOD;
  }

  return hash.toString(16).padStart(8, '0');
}

// ============================================================================
// Feature Extraction
// ============================================================================

function computeTickStats(window: TickWindow): Record<string, number> {
  const ticks = window.signals.map((s) => extractTick(s));
  const min = Math.min(...ticks);
  const max = Math.max(...ticks);
  const range = max - min + 1;
  const unique = new Set(ticks).size;

  return {
    tickMin: min,
    tickMax: max,
    tickRange: range,
    tickUnique: unique,
    tickDensity: window.signals.length / range,
  };
}

function computeSequenceStats(window: TickWindow): Record<string, number> {
  const sequences = window.signals.map((s) => extractSequence(s));
  const min = Math.min(...sequences);
  const max = Math.max(...sequences);
  const unique = new Set(sequences).size;

  return {
    seqMin: min,
    seqMax: max,
    seqUnique: unique,
  };
}

function computeNodeDistribution(window: TickWindow): Record<string, number> {
  const distribution: Record<string, number> = {};
  for (const signal of window.signals) {
    const node = signal.node ?? 'unknown';
    distribution[node] = (distribution[node] ?? 0) + 1;
  }

  const total = window.signals.length;
  const normalized: Record<string, number> = {};
  for (const [node, count] of Object.entries(distribution)) {
    normalized[`node_${node}_ratio`] = count / total;
    normalized[`node_${node}_count`] = count;
  }

  return normalized;
}

function computeValueStats(window: TickWindow): Record<string, number> {
  const values = window.signals.map((s) => s.value ?? 0);
  const sum = values.reduce((a, b) => a + b, 0);
  const mean = sum / values.length;
  const sorted = [...values].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const variance = values.reduce((acc, v) => acc + Math.pow(v - mean, 2), 0) / values.length;

  return {
    valueSum: sum,
    valueMean: mean,
    valueMedian: median,
    valueVariance: variance,
    valueStdDev: Math.sqrt(variance),
    valueMin: sorted[0],
    valueMax: sorted[sorted.length - 1],
  };
}

// ============================================================================
// Public API
// ============================================================================

const DEFAULT_CONFIG: FeatureVectorConfig = {
  includeTickStats: true,
  includeSequenceStats: true,
  includeNodeDistribution: true,
  includeValueStats: true,
};

/**
 * Creates a deterministic feature vector from a tick window.
 * Same window always produces identical feature vector.
 *
 * @example
 * ```typescript
 * const signals = createTestSignals(20);
 * const windows = createFixedTickWindows(signals, { windowSize: 10, overlap: 0 });
 * const vector = createFeatureVector(windows[0]);
 * // vector.receipt.featureHash is deterministic
 * ```
 */
export function createFeatureVector(
  window: TickWindow,
  config: Partial<FeatureVectorConfig> = {},
): FeatureVector {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const dimensions: Record<string, number> = {};

  // Add window metadata
  dimensions['windowStartTick'] = window.startTick;
  dimensions['windowEndTick'] = window.endTick;
  dimensions['signalCount'] = window.signals.length;

  // Add tick statistics
  if (cfg.includeTickStats) {
    Object.assign(dimensions, computeTickStats(window));
  }

  // Add sequence statistics
  if (cfg.includeSequenceStats) {
    Object.assign(dimensions, computeSequenceStats(window));
  }

  // Add node distribution
  if (cfg.includeNodeDistribution) {
    Object.assign(dimensions, computeNodeDistribution(window));
  }

  // Add value statistics
  if (cfg.includeValueStats) {
    Object.assign(dimensions, computeValueStats(window));
  }

  // Compute deterministic receipt
  const featureHash = hashFeatureVector(dimensions);
  const vectorId = `${window.id}-${featureHash}`;

  const receipt: FeatureVectorReceipt = {
    vectorId,
    windowReceipt: window.receipt,
    dimensions: Object.keys(dimensions).sort(),
    featureHash,
    timestamp: Date.now(),
  };

  return {
    id: vectorId,
    windowId: window.id,
    dimensions,
    receipt,
  };
}

/**
 * Verifies feature vector determinism.
 * Re-computing from same window should produce identical vector.
 */
export function verifyFeatureVectorDeterminism(vector: FeatureVector, window: TickWindow): boolean {
  const recomputed = createFeatureVector(window);
  return recomputed.receipt.featureHash === vector.receipt.featureHash;
}

/**
 * Creates feature vectors for multiple windows.
 */
export function createFeatureVectors(
  windows: TickWindow[],
  config?: Partial<FeatureVectorConfig>,
): FeatureVector[] {
  return windows.map((w) => createFeatureVector(w, config));
}

/**
 * Computes cosine similarity between two feature vectors.
 * Returns value in range [-1, 1].
 */
export function computeCosineSimilarity(a: FeatureVector, b: FeatureVector): number {
  const dimsA = a.dimensions;
  const dimsB = b.dimensions;
  const allDims = new Set([...Object.keys(dimsA), ...Object.keys(dimsB)]);

  let dotProduct = 0;
  let normA = 0;
  let normB = 0;

  for (const dim of allDims) {
    const valA = dimsA[dim] ?? 0;
    const valB = dimsB[dim] ?? 0;
    dotProduct += valA * valB;
    normA += valA * valA;
    normB += valB * valB;
  }

  if (normA === 0 || normB === 0) return 0;
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

/**
 * Computes Euclidean distance between two feature vectors.
 */
export function computeEuclideanDistance(a: FeatureVector, b: FeatureVector): number {
  const dimsA = a.dimensions;
  const dimsB = b.dimensions;
  const allDims = new Set([...Object.keys(dimsA), ...Object.keys(dimsB)]);

  let sumSquared = 0;
  for (const dim of allDims) {
    const diff = (dimsA[dim] ?? 0) - (dimsB[dim] ?? 0);
    sumSquared += diff * diff;
  }

  return Math.sqrt(sumSquared);
}
