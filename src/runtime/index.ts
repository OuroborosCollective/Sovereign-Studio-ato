/**
 * Runtime Intelligence Library
 * 
 * Unified exports for the runtime intelligence system.
 * 
 * @module runtime
 */

import {
  runtimeIntelligence as baseRuntimeIntelligence,
  type RuntimeIntelligenceConfig,
} from './RuntimeIntelligence';
import {
  createRuntimeRepoSnapshot,
  saveRuntimeRepoSnapshot,
  loadRuntimeRepoSnapshot,
  clearRuntimeRepoSnapshot,
} from './repoSnapshotRuntime';

export {
  // Main class
  RuntimeIntelligence,
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

type BaseRuntimeIntelligence = typeof baseRuntimeIntelligence;

export type RuntimeIntelligenceWithRepoSnapshot = BaseRuntimeIntelligence & {
  createRepoSnapshot: typeof createRuntimeRepoSnapshot;
  saveRepoSnapshot: typeof saveRuntimeRepoSnapshot;
  loadRepoSnapshot: typeof loadRuntimeRepoSnapshot;
  clearRepoSnapshot: typeof clearRuntimeRepoSnapshot;
};

/**
 * Default singleton instance with repo snapshot runtime methods attached.
 *
 * This keeps the public API ergonomic for app handoff flows:
 * runtimeIntelligence.saveRepoSnapshot(...)
 * runtimeIntelligence.loadRepoSnapshot(...)
 */
export const runtimeIntelligence: RuntimeIntelligenceWithRepoSnapshot = Object.assign(baseRuntimeIntelligence, {
  createRepoSnapshot: createRuntimeRepoSnapshot,
  saveRepoSnapshot: saveRuntimeRepoSnapshot,
  loadRepoSnapshot: loadRuntimeRepoSnapshot,
  clearRepoSnapshot: clearRuntimeRepoSnapshot,
});
