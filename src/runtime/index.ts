/**
 * Runtime Intelligence Library
 * 
 * Unified exports for the runtime intelligence system.
 * 
 * @module runtime
 */

export {
  // Main class
  RuntimeIntelligence,
  runtimeIntelligence,
  createRuntimeIntelligence,
  
  // Types
  type TraceId,
  type RuntimeContext,
  type RuntimeDecision,
  type RuntimeGuardResult,
  type TelemetryEvent,
  type Guard,
  type GuardChainConfig,
  
  // Utilities
  RuntimeCircuitBreaker,
  RuntimeGuardError,
  runGuardChain,
  
  // React hook
  useRuntimeIntelligence,
  type UseRuntimeIntelligenceOptions,
} from './RuntimeIntelligence';
