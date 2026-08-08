/**
 * Predictive Pipeline Module
 *
 * Deterministic signal processing pipeline for runtime sensors.
 * Provides bounded iterables, ordering, and replay capability.
 *
 * @module predictive/pipeline
 */

export {
  type SignalOrderKey,
  type OrderedSignal,
  type SignalOrderingOptions,
  extractTick,
  extractSequence,
  createOrderKey,
  compareOrderKeys,
  withOrderKey,
  orderSignals,
  groupByNode,
  verifyOrder,
  DEFAULT_ORDERING_OPTIONS,
} from './signalOrdering';

export {
  type ChunkResult,
  type PairResult,
  type GroupResult,
  type MinMaxResult,
  type ChunkOptions,
  type ChunkOverlapOptions,
  LengthMismatchError,
  chunkwise,
  chunkwiseOverlap,
  pairwise,
  zipEqual,
  groupBy,
  runningDifference,
  runningTotal,
  toMinMax,
  validateDeterministic,
} from './deterministicIterables';

export {
  type TickWindow,
  type TickWindowReceipt,
  type TickWindowConfig,
  type TickWindowStats,
  createFixedTickWindows,
  createOverlapTickWindows,
  createBoundedTickWindows,
  verifyWindowDeterminism,
  getUniqueTicks,
  groupByTick,
  computeTickWindowStats,
} from './tickWindow';

export { createFeatureVector } from './featureVector';
