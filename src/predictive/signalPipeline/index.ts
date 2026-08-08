/**
 * Signal Pipeline - Deterministic tick windows with replay parity
 * 
 * @module predictive/signalPipeline
 */

// Contracts
export {
  SignalTickContract,
  SignalWindowContract,
  SIGNAL_TICK_SCHEMA_ID,
  SIGNAL_WINDOW_SCHEMA_ID,
  validateSignalTick,
  validateSignalWindow,
  generateSignalTickSchemaHash,
  generateSignalWindowSchemaHash,
  type ValidationResult,
  type ValidationError,
  type ValidationWarning,
} from './signalTick';

// Processor
export {
  BackpressureController,
  BoundedSignalIterator,
  ReplayParityValidator,
  createSignalTick,
  type BackpressureConfig,
  type BackpressureState,
  type SignalIteratorOptions,
  type SignalBatch,
  type ReplayParityResult,
  type ReplayMismatch,
  DEFAULT_BACKPRESSURE_CONFIG,
} from './signalProcessor';
