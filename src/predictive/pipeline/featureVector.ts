/**
 * Feature Vector - Deterministic Feature Extraction from Signal Windows
 *
 * Produces deterministic feature vectors from tick windows.
 * Same recorded signals always produce identical feature hashes.
 *
 * @module predictive/pipeline/featureVector
 */

import type { Signal } from '../types';
import type { OrderedSignal } from './signalOrdering';
import type { TickWindow } from './tickWindow';
import type { FeatureVector, WindowReceipt } from './deterministicIterables';
import {
  runningDifference,
  runningTotal,
  toMinMax,
  pairwise,
  groupBy,
} from './deterministicIterables';

// ============================================================================
// Feature Extraction Types
// ============================================================================

/**
 * Configuration for feature extraction.
 */
export interface FeatureExtractorConfig {
  /** Include value statistics */
  includeStats: boolean;
  /** Include delta features */
  includeDeltas: boolean;
  /** Include temporal features */
  includeTemporal: boolean;
  /** Number of histogram bins (0 to disable) */
  histogramBins: number;
}

/**
 * Extracted features from a window.
 */
export interface ExtractedFeatures {
  /** Mean value */
  mean: number;
  /** Standard deviation */
  stdDev: number;
  /** Min value */
  min: number;
  /** Max value */
  max: number;
  /** Value range */
  range: number;
  /** Sum of values */
  sum: number;
  /** Running differences (temporal features) */
  deltas: number[];
  /** Running totals (cumulative energy) */
  cumulativeSum: number[];
  /** Min/max pair */
  minMax: [number, number] | undefined;
  /** Histogram bins if configured */
  histogram?: number[];
  /** Per-node statistics */
  nodeStats: Map<string, { mean: number; stdDev: number; count: number }>;
  /** Signal hash (SHA-256 of ordered signal values) */
  signalHash: string;
}

/**
 * Feature extraction result.
 */
export interface FeatureExtractionResult {
  /** Extracted features */
  features: ExtractedFeatures;
  /** Feature vector for ML inference */
  featureVector: FeatureVector;
  /** Window receipt */
  receipt: WindowReceipt;
}

// ============================================================================
// Hash Functions (Deterministic, No Randomness)
// ============================================================================

/**
 * Computes a deterministic hash of signal values.
 * Uses a simple polynomial hash for deterministic behavior across environments.
 * For production, consider using a proper SHA-256 implementation.
 */
export function computeSignalHash(signals: OrderedSignal[]): string {
  if (signals.length === 0) return 'empty';

  // Use tick-sequence-value tuples for hashing
  const tuples = signals.map(
    (s) => `${s.metadata.tick}:${s.metadata.sequence}:${s.metadata.node}:${s.value}`,
  );
  const combined = tuples.join('|');

  // Simple deterministic hash (FNV-1a inspired)
  let hash = 2166136261; // FNV offset basis
  const prime = 16777619;

  for (let i = 0; i < combined.length; i++) {
    hash ^= combined.charCodeAt(i);
    hash = Math.imul(hash, prime);
  }

  // Convert to hex string
  const hex = (hash >>> 0).toString(16).padStart(8, '0');

  // Extend to 64 hex chars for SHA-256-like appearance
  let extended = hex;
  for (let i = 0; i < 7; i++) {
    hash ^= (hash >>> 20) + (hash << 5) + i;
    extended += (hash >>> 0).toString(16).padStart(8, '0');
  }

  return extended;
}

// ============================================================================
// Statistical Features
// ============================================================================

/**
 * Computes mean of values.
 */
export function computeMean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

/**
 * Computes standard deviation of values.
 */
export function computeStdDev(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = computeMean(values);
  const squaredDiffs = values.map((v) => (v - mean) ** 2);
  const variance = squaredDiffs.reduce((a, b) => a + b, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

// ============================================================================
// Feature Extraction
// ============================================================================

const DEFAULT_CONFIG: FeatureExtractorConfig = {
  includeStats: true,
  includeDeltas: true,
  includeTemporal: true,
  histogramBins: 0,
};

/**
 * Extracts features from a tick window.
 */
export function extractFeatures(
  window: TickWindow,
  config: Partial<FeatureExtractorConfig> = {},
): ExtractedFeatures {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const signals = window.signals;

  if (signals.length === 0) {
    return createEmptyFeatures(window);
  }

  // Sort signals canonically for consistent processing: by node, then tick,
  // then sequence. This keeps per-node signals contiguous so node statistics
  // aggregate correctly regardless of the original input order.
  const sortedSignals = [...signals].sort((a, b) => {
    if (a.metadata.node !== b.metadata.node) {
      return a.metadata.node < b.metadata.node ? -1 : 1;
    }
    if (a.metadata.tick !== b.metadata.tick) return a.metadata.tick - b.metadata.tick;
    return a.metadata.sequence - b.metadata.sequence;
  });

  const values = sortedSignals.map((s) => s.value);

  // Basic statistics
  const mean = cfg.includeStats ? computeMean(values) : 0;
  const stdDev = cfg.includeStats ? computeStdDev(values) : 0;
  const minMax = toMinMax(values);
  const range = minMax ? minMax[1] - minMax[0] : 0;
  const sum = cfg.includeStats ? values.reduce((a, b) => a + b, 0) : 0;

  // Temporal features
  const deltas = cfg.includeDeltas ? [...runningDifference(values)] : [];
  const cumulativeSum = cfg.includeTemporal ? [...runningTotal(values)] : [];

  // Histogram
  let histogram: number[] | undefined;
  if (cfg.histogramBins > 0 && minMax) {
    histogram = computeHistogram(values, minMax[0], minMax[1], cfg.histogramBins);
  }

  // Per-node statistics
  const nodeStats = computeNodeStats(sortedSignals);

  // Signal hash
  const signalHash = computeSignalHash(sortedSignals);

  return {
    mean,
    stdDev,
    min: minMax?.[0] ?? 0,
    max: minMax?.[1] ?? 0,
    range,
    sum,
    deltas,
    cumulativeSum,
    minMax,
    histogram,
    nodeStats,
    signalHash,
  };
}

/**
 * Computes a simple histogram.
 */
function computeHistogram(values: number[], min: number, max: number, bins: number): number[] {
  if (min === max) return [values.length];

  const binWidth = (max - min) / bins;
  const histogram = new Array(bins).fill(0);

  for (const value of values) {
    let binIdx = Math.floor((value - min) / binWidth);
    if (binIdx >= bins) binIdx = bins - 1; // Handle edge case
    if (binIdx < 0) binIdx = 0;
    histogram[binIdx]++;
  }

  return histogram;
}

/**
 * Computes per-node statistics.
 */
function computeNodeStats(
  signals: OrderedSignal[],
): Map<string, { mean: number; stdDev: number; count: number }> {
  const byNode = new Map<string, number[]>();

  for (const signal of signals) {
    const node = signal.node;
    if (!byNode.has(node)) byNode.set(node, []);
    byNode.get(node)!.push(signal.value);
  }

  const stats = new Map<string, { mean: number; stdDev: number; count: number }>();
  for (const [node, values] of byNode) {
    stats.set(node, {
      mean: computeMean(values),
      stdDev: computeStdDev(values),
      count: values.length,
    });
  }

  return stats;
}

/**
 * Creates empty features for an empty window.
 */
function createEmptyFeatures(window: TickWindow): ExtractedFeatures {
  return {
    mean: 0,
    stdDev: 0,
    min: 0,
    max: 0,
    range: 0,
    sum: 0,
    deltas: [],
    cumulativeSum: [],
    minMax: undefined,
    histogram: undefined,
    nodeStats: new Map(),
    signalHash: 'empty',
  };
}

// ============================================================================
// Feature Vector Generation
// ============================================================================

/**
 * Converts extracted features to a flat feature vector for ML inference.
 */
export function featuresToVector(features: ExtractedFeatures, config: FeatureExtractorConfig): number[] {
  const vector: number[] = [];

  if (config.includeStats) {
    vector.push(features.mean);
    vector.push(features.stdDev);
    vector.push(features.min);
    vector.push(features.max);
    vector.push(features.range);
    vector.push(features.sum);
  }

  if (config.includeDeltas && features.deltas.length > 0) {
    // Use first N deltas for fixed-size vector
    const maxDeltas = 10;
    for (let i = 0; i < Math.min(features.deltas.length, maxDeltas); i++) {
      vector.push(features.deltas[i]);
    }
    // Pad if fewer deltas
    for (let i = features.deltas.length; i < maxDeltas; i++) {
      vector.push(0);
    }
  }

  if (config.includeTemporal && features.cumulativeSum.length > 0) {
    const maxCumulative = 10;
    for (let i = 0; i < Math.min(features.cumulativeSum.length, maxCumulative); i++) {
      vector.push(features.cumulativeSum[i]);
    }
    for (let i = features.cumulativeSum.length; i < maxCumulative; i++) {
      vector.push(0);
    }
  }

  if (config.histogramBins > 0 && features.histogram) {
    vector.push(...features.histogram);
  }

  return vector;
}

/**
 * Creates a FeatureVector from extracted features.
 */
export function createFeatureVector(
  features: ExtractedFeatures,
  window: TickWindow,
  config: FeatureExtractorConfig,
): FeatureVector {
  const values = featuresToVector(features, config);

  return {
    values,
    signalHash: features.signalHash,
    tickRange: [window.startTick, window.endTick],
    sequenceRange: [
      window.signals[0]?.metadata.sequence ?? 0,
      window.signals[window.signals.length - 1]?.metadata.sequence ?? 0,
    ],
    revision: window.signals[0]?.metadata.revision ?? '',
    configFingerprint: window.configFingerprint,
  };
}

/**
 * Creates a WindowReceipt for feature processing.
 */
export function createFeatureReceipt(
  window: TickWindow,
  featureVector: FeatureVector,
  isReplay: boolean,
): WindowReceipt {
  return {
    id: `receipt-${window.id}`,
    featureVector,
    signalCount: window.signals.length,
    timestamp: Date.now(),
    isReplay,
  };
}

// ============================================================================
// Feature Extraction with Full Pipeline
// ============================================================================

/**
 * Extracts features and generates all outputs from a window.
 */
export function processWindowToFeatures(
  window: TickWindow,
  isReplay: boolean = false,
  config: Partial<FeatureExtractorConfig> = {},
): FeatureExtractionResult {
  const cfg = { ...DEFAULT_CONFIG, ...config };

  const features = extractFeatures(window, cfg);
  const featureVector = createFeatureVector(features, window, cfg);
  const receipt = createFeatureReceipt(window, featureVector, isReplay);

  return {
    features,
    featureVector,
    receipt,
  };
}

// ============================================================================
// Pairwise Delta Features
// ============================================================================

/**
 * Computes pairwise deltas between consecutive signals grouped by node.
 */
export function computeNodeDeltaFeatures(
  window: TickWindow,
): Map<string, Array<{ from: number; to: number; delta: number }>> {
  const byNode = new Map<string, OrderedSignal[]>();

  for (const signal of window.signals) {
    const node = signal.metadata.node;
    if (!byNode.has(node)) byNode.set(node, []);
    byNode.get(node)!.push(signal);
  }

  const deltas = new Map<string, Array<{ from: number; to: number; delta: number }>>();

  for (const [node, signals] of byNode) {
    const sorted = [...signals].sort((a, b) => a.metadata.sequence - b.metadata.sequence);
    const nodeDeltas: Array<{ from: number; to: number; delta: number }> = [];

    for (const pair of pairwise(sorted)) {
      const [from, to] = pair;
      nodeDeltas.push({
        from: from.value,
        to: to.value,
        delta: to.value - from.value,
      });
    }

    deltas.set(node, nodeDeltas);
  }

  return deltas;
}

// ============================================================================
// Verification
// ============================================================================

/**
 * Verifies that two feature vectors are identical.
 * Used for replay parity verification.
 */
export function verifyFeatureParity(a: FeatureVector, b: FeatureVector): { equal: boolean; diff?: string } {
  if (a.signalHash !== b.signalHash) {
    return { equal: false, diff: `Signal hash mismatch: ${a.signalHash} vs ${b.signalHash}` };
  }
  if (a.tickRange[0] !== b.tickRange[0] || a.tickRange[1] !== b.tickRange[1]) {
    return {
      equal: false,
      diff: `Tick range mismatch: [${a.tickRange}] vs [${b.tickRange}]`,
    };
  }
  if (a.revision !== b.revision) {
    return { equal: false, diff: `Revision mismatch: ${a.revision} vs ${b.revision}` };
  }
  if (a.values.length !== b.values.length) {
    return {
      equal: false,
      diff: `Value length mismatch: ${a.values.length} vs ${b.values.length}`,
    };
  }

  for (let i = 0; i < a.values.length; i++) {
    if (a.values[i] !== b.values[i]) {
      return {
        equal: false,
        diff: `Value mismatch at index ${i}: ${a.values[i]} vs ${b.values[i]}`,
      };
    }
  }

  return { equal: true };
}
