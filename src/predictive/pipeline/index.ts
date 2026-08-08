/**
 * Deterministic Signal Pipeline - public surface.
 *
 * Issue #1170: only the allowlisted, deterministic functions are re-exported.
 * The iterable primitives (`deterministicIterables`) are intentionally NOT
 * re-exported here as a wildcard; the contract test pins their exact surface.
 *
 * @module predictive/pipeline
 */

export {
  type PipelineSignal,
  canonicalSignalCompare,
  canonicalOrder,
  findDuplicateKeys,
  groupByNode,
} from './signalOrdering';

export {
  type TickWindowConfig,
  type TickWindow,
  type TickWindowSlice,
  type SignalDrop,
  type DropReasonCode,
  type WindowingResult,
  DEFAULT_TICK_WINDOW_CONFIG,
  signalTickHash,
  tickWindowConfigHash,
  buildTickWindows,
  computeWindowDeltas,
  pairwiseWindowHashes,
} from './tickWindow';

export {
  type FeatureVector,
  type FeatureReceipt,
  type FeatureDescriptorName,
  FEATURE_DESCRIPTOR_NAMES,
  extractFeature,
  buildFeatureReceipt,
  verifyFeatureReceipt,
} from './featureExtraction';

export {
  type PipelineConfig,
  type SignalPipelineResult,
  DEFAULT_PIPELINE_CONFIG,
  runSignalPipeline,
  runSignalPipelineAsync,
  assertReplayParity,
} from './signalPipeline';

export { DETERMINISTIC_ITERABLE_ALLOWLIST } from './deterministicIterables';
