/**
 * Deterministic Signal Pipeline
 *
 * A deterministic signal and feature pipeline for runtime sensors.
 * Uses only approved iterator primitives for reproducible processing.
 *
 * @module predictive/pipeline
 */

// Core deterministic iterables
export {
  chunkwise,
  chunkwiseOverlap,
  pairwise,
  zipEqual,
  zipEqualN,
  groupBy,
  groupByNode,
  runningDifference,
  runningTotal,
  toMinMax,
  withBoundedIteration,
  LengthMismatchError,
  DEFAULT_DETERMINISTIC_CONFIG,
  BLOCKED_PATTERNS,
  DETERMINISTIC_ITERABLE_EXPORTS,
} from './deterministicIterables';

export type {
  DeterministicIterableConfig,
  PipelineItem,
  ChunkResult,
  PairResult,
  RunningDiffResult,
  RunningTotalResult,
  MinMaxResult,
  BoundedIterationOptions,
} from './deterministicIterables';

// Signal ordering
export {
  orderSignals,
  toOrderedSignal,
  groupSignalsByNode,
  mergeNodeSignals,
  validateCanonicalOrder,
  processSignals,
  createOrderingFingerprint,
  signalOrderingKey,
  signalOrderingComparator,
} from './signalOrdering';

export type {
  OrderedSignal,
  SignalOrderingOptions,
  OrderablePipelineItem,
} from './signalOrdering';

// Tick windows
export {
  fixedTickWindows,
  overlappingTickWindows,
  tickWindows,
  processSignalsToWindows,
  createWindowFingerprint,
  createBackpressureController,
} from './tickWindow';

export type {
  WindowType,
  TickWindowConfig,
  TickWindow,
  TickWindowMetadata,
  TickWindowReceipt,
  BackpressureState,
} from './tickWindow';

// Feature vectors
export {
  computeFeatureVector,
  computeDeltas,
  processChunkToFeatureVectors,
  validateDeterminism,
  createFeatureConfigFingerprint,
} from './featureVector';

export type {
  FeatureVectorConfig,
  FeatureVector,
  FeatureVectorMetadata,
  SignalDelta,
} from './featureVector';

// Replay
export {
  createRecordedSet,
  validateReplayable,
  replay,
  liveProcess,
  compareLiveReplayParity,
  createParityReceipt,
} from './replay';

export {
  ReplayError,
  RevisionMismatchError,
} from './replay';

export type {
  RecordedSignalSet,
  ReplayConfig,
  ReplayResult,
  ParityReceipt,
} from './replay';
