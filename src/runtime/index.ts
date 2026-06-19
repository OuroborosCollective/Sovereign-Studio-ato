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
  type TraceIdProvider,
  type RuntimeContext,
  type RuntimeDecision,
  type RuntimeGuardResult,
  type TelemetryEvent,
  type Guard,
  type GuardChainConfig,
  type RuntimeIntelligenceConfig,
  
  // Utilities
  RuntimeCircuitBreaker,
  RuntimeGuardError,
  runGuardChain,
  defaultTraceIdProvider,
  
  // React hook
  useRuntimeIntelligence,
  type UseRuntimeIntelligenceOptions,
} from './RuntimeIntelligence';

export {
  createRuntimeRepoSnapshot,
  saveRuntimeRepoSnapshot,
  loadRuntimeRepoSnapshot,
  clearRuntimeRepoSnapshot,
  type RuntimeRepoSnapshotInput,
  type RuntimeRepoSnapshotResult,
} from './repoSnapshotRuntime';
