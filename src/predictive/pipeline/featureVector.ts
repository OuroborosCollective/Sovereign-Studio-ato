/**
 * Feature Vector Module
 *
 * Creates deterministic feature vectors from signal windows.
 * Same recorded signals always produce identical Feature Hash.
 *
 * Features:
 * - Deterministic vector computation
 * - Pairwise deltas between consecutive signals
 * - Config fingerprint included in hash
 * - No wall-clock dependencies
 *
 * @module predictive/pipeline/featureVector
 */

import type { OrderedSignal } from './signalOrdering';
import type { TickWindow } from './tickWindow';
import type { ChunkResult } from './deterministicIterables';

/**
 * Feature vector configuration.
 */
export interface FeatureVectorConfig {
  /** Include delta features */
  includeDeltas: boolean;
  /** Include node-wise aggregation */
  includeNodeAggregation: boolean;
  /** Include tick-wise aggregation */
  includeTickAggregation: boolean;
  /** Number of bins for value histogram */
  histogramBins: number;
  /** Revision hash */
  revision: string;
  /** Window fingerprint for cache validation */
  windowFingerprint: string;
}

/**
 * Default feature vector configuration.
 */
export const DEFAULT_FEATURE_VECTOR_CONFIG: FeatureVectorConfig = {
  includeDeltas: true,
  includeNodeAggregation: true,
  includeTickAggregation: true,
  histogramBins: 10,
  revision: 'default',
  windowFingerprint: 'default',
};

/**
 * Feature vector result.
 */
export interface FeatureVector {
  /** Feature ID */
  id: string;
  /** Dense feature array */
  features: number[];
  /** Feature metadata */
  metadata: FeatureVectorMetadata;
  /** Deterministic hash of features */
  hash: string;
}

/**
 * Metadata for a feature vector.
 */
export interface FeatureVectorMetadata {
  /** Signal count used */
  signalCount: number;
  /** Unique nodes */
  nodes: string[];
  /** Tick range */
  tickRange: [number, number];
  /** Dimensionality */
  dimensions: number;
  /** Configuration fingerprint */
  configFingerprint: string;
  /** Window ID this vector was computed from */
  windowId: string;
}

/**
 * Pairwise delta between signals.
 */
export interface SignalDelta {
  node: string;
  fromValue: number;
  toValue: number;
  delta: number;
  tick: number;
}

/**
 * Creates a deterministic feature vector ID.
 */
function createFeatureId(windowId: string, configHash: string): string {
  return `fv-${windowId}-${configHash.slice(0, 8)}`;
}

/**
 * Creates a deterministic hash of feature values.
 * Uses a simple but deterministic hash function.
 */
function hashFeatures(features: number[], seed: string): string {
  let hash = 0;
  // Seed from string
  for (let i = 0; i < seed.length; i++) {
    const char = seed.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  // Mix in feature values
  for (let i = 0; i < features.length; i++) {
    // Normalize feature value
    const normalized = Math.abs(features[i] % 1000000) / 1000000;
    hash = ((hash << 5) - hash) + Math.floor(normalized * 1000000);
    hash = hash ^ (i * 2654435761); // Golden ratio rotation
    hash = hash & hash;
  }
  // Convert to hex string
  const hex = (hash >>> 0).toString(16);
  return hex.padStart(8, '0');
}

/**
 * Computes pairwise deltas between consecutive signals.
 */
export function computeDeltas(signals: OrderedSignal[]): SignalDelta[] {
  const deltas: SignalDelta[] = [];

  for (let i = 1; i < signals.length; i++) {
    const prev = signals[i - 1];
    const curr = signals[i];

    if (prev.node === curr.node) {
      deltas.push({
        node: curr.node,
        fromValue: prev.value,
        toValue: curr.value,
        delta: curr.value - prev.value,
        tick: curr.tick,
      });
    }
  }

  return deltas;
}

/**
 * Creates value histogram features.
 */
function createHistogram(values: number[], bins: number): number[] {
  if (values.length === 0) {
    return new Array(bins).fill(0);
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const binWidth = range / bins;

  const histogram = new Array(bins).fill(0);

  for (const value of values) {
    const binIndex = Math.min(Math.floor((value - min) / binWidth), bins - 1);
    histogram[binIndex]++;
  }

  // Normalize
  const total = values.length;
  return histogram.map((count) => count / total);
}

/**
 * Aggregates values by node.
 */
function aggregateByNode(
  signals: OrderedSignal[],
): Map<string, { sum: number; count: number; min: number; max: number; mean: number }> {
  const nodeMap = new Map<string, number[]>();

  for (const signal of signals) {
    const values = nodeMap.get(signal.node) || [];
    values.push(signal.value);
    nodeMap.set(signal.node, values);
  }

  const result = new Map<string, { sum: number; count: number; min: number; max: number; mean: number }>();

  for (const [node, values] of nodeMap) {
    const sum = values.reduce((a, b) => a + b, 0);
    const count = values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);
    result.set(node, {
      sum,
      count,
      min,
      max,
      mean: sum / count,
    });
  }

  return result;
}

/**
 * Aggregates values by tick.
 */
function aggregateByTick(
  signals: OrderedSignal[],
): Map<number, { sum: number; count: number; mean: number }> {
  const tickMap = new Map<number, number[]>();

  for (const signal of signals) {
    const values = tickMap.get(signal.tick) || [];
    values.push(signal.value);
    tickMap.set(signal.tick, values);
  }

  const result = new Map<number, { sum: number; count: number; mean: number }>();

  for (const [tick, values] of tickMap) {
    const sum = values.reduce((a, b) => a + b, 0);
    result.set(tick, {
      sum,
      count: values.length,
      mean: sum / values.length,
    });
  }

  return result;
}

/**
 * Creates the config fingerprint for feature vectors.
 */
export function createFeatureConfigFingerprint(config: FeatureVectorConfig): string {
  return `fv:${config.includeDeltas}:${config.includeNodeAggregation}:${config.includeTickAggregation}:${config.histogramBins}:${config.revision}:${config.windowFingerprint}`;
}

/**
 * Computes a deterministic feature vector from signals.
 */
export function computeFeatureVector(
  signals: OrderedSignal[],
  window: TickWindow,
  config: FeatureVectorConfig = DEFAULT_FEATURE_VECTOR_CONFIG,
): FeatureVector {
  const features: number[] = [];
  const nodes = [...new Set(signals.map((s) => s.node))];
  const ticks = [...new Set(signals.map((s) => s.tick))];
  const tickRange: [number, number] = ticks.length > 0
    ? [Math.min(...ticks), Math.max(...ticks)]
    : [0, 0];

  // 1. Basic statistics
  if (signals.length > 0) {
    const values = signals.map((s) => s.value);
    const sum = values.reduce((a, b) => a + b, 0);
    const mean = sum / values.length;
    const variance = values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / values.length;

    features.push(
      signals.length,
      sum,
      mean,
      Math.min(...values),
      Math.max(...values),
      variance,
      Math.sqrt(variance), // Std dev
    );
  } else {
    features.push(0, 0, 0, 0, 0, 0, 0);
  }

  // 2. Delta features
  if (config.includeDeltas) {
    const deltas = computeDeltas(signals);
    if (deltas.length > 0) {
      const deltaValues = deltas.map((d) => d.delta);
      features.push(
        deltas.length,
        Math.min(...deltaValues),
        Math.max(...deltaValues),
        deltaValues.reduce((a, b) => a + b, 0) / deltaValues.length,
      );
    } else {
      features.push(0, 0, 0, 0);
    }
  }

  // 3. Node-wise aggregation
  if (config.includeNodeAggregation) {
    const nodeAgg = aggregateByNode(signals);
    features.push(nodeAgg.size); // Number of nodes

    // Aggregate across nodes
    let totalNodeSum = 0;
    let totalNodeCount = 0;
    let nodeMeanValues: number[] = [];

    for (const agg of nodeAgg.values()) {
      totalNodeSum += agg.sum;
      totalNodeCount += agg.count;
      nodeMeanValues.push(agg.mean);
    }

    features.push(totalNodeSum, totalNodeCount);
    if (nodeMeanValues.length > 0) {
      const globalNodeMean = nodeMeanValues.reduce((a, b) => a + b, 0) / nodeMeanValues.length;
      features.push(globalNodeMean);
    } else {
      features.push(0);
    }
  }

  // 4. Tick-wise aggregation
  if (config.includeTickAggregation) {
    const tickAgg = aggregateByTick(signals);
    features.push(tickAgg.size); // Number of ticks

    // Aggregate across ticks
    let tickMeanValues: number[] = [];
    for (const agg of tickAgg.values()) {
      tickMeanValues.push(agg.mean);
    }

    if (tickMeanValues.length > 0) {
      const globalTickMean = tickMeanValues.reduce((a, b) => a + b, 0) / tickMeanValues.length;
      features.push(globalTickMean);
    } else {
      features.push(0);
    }
  }

  // 5. Histogram features
  if (signals.length > 0) {
    const histogram = createHistogram(signals.map((s) => s.value), config.histogramBins);
    features.push(...histogram);
  } else {
    features.push(...new Array(config.histogramBins).fill(0));
  }

  // Create metadata
  const configFingerprint = createFeatureConfigFingerprint(config);
  const metadata: FeatureVectorMetadata = {
    signalCount: signals.length,
    nodes,
    tickRange,
    dimensions: features.length,
    configFingerprint,
    windowId: window.id,
  };

  // Create deterministic hash
  const hash = hashFeatures(features, `${config.revision}:${window.id}`);

  return {
    id: createFeatureId(window.id, hash),
    features,
    metadata,
    hash,
  };
}

/**
 * Processes a chunk of signals into feature vectors.
 */
export function processChunkToFeatureVectors(
  chunk: ChunkResult<OrderedSignal>,
  config: FeatureVectorConfig = DEFAULT_FEATURE_VECTOR_CONFIG,
): FeatureVector[] {
  const vectors: FeatureVector[] = [];

  // Create a synthetic window for the chunk
  const window: TickWindow = {
    id: `chunk-${chunk.startIndex}`,
    startTick: chunk.startIndex,
    endTick: chunk.endIndex,
    signals: chunk.items,
    metadata: {
      signalCount: chunk.items.length,
      isPartial: chunk.isPartial,
      hadDrop: false,
      nodes: [...new Set(chunk.items.map((s) => s.node))],
      tickRange: [chunk.startIndex, chunk.endIndex],
      windowType: 'fixed',
    },
  };

  vectors.push(computeFeatureVector(chunk.items, window, config));

  return vectors;
}

/**
 * Validates feature vector determinism.
 * Same inputs should always produce same hash.
 */
export function validateDeterminism(
  signals: OrderedSignal[],
  window: TickWindow,
  config: FeatureVectorConfig,
  iterations: number = 5,
): { deterministic: boolean; hashes: string[] } {
  const hashes: string[] = [];

  for (let i = 0; i < iterations; i++) {
    const vector = computeFeatureVector(signals, window, config);
    hashes.push(vector.hash);
  }

  const allSame = hashes.every((h) => h === hashes[0]);

  return {
    deterministic: allSame,
    hashes,
  };
}
