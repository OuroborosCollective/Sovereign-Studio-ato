/**
 * Runtime Intelligence Library
 *
 * Unified public exports for the runtime intelligence system.
 *
 * This file is the stable handoff surface for app/runtime integration.
 *
 * @module runtime
 */

import {
  createRuntimeIntelligence as createBaseRuntimeIntelligence,
  runtimeIntelligence as baseRuntimeIntelligence,
} from './RuntimeIntelligence';

import type { RuntimeIntelligenceConfig } from './RuntimeIntelligence';

import {
  clearRuntimeRepoSnapshot,
  createRuntimeRepoSnapshot,
  loadRuntimeRepoSnapshot,
  saveRuntimeRepoSnapshot,
} from './repoSnapshotRuntime';

export {
  RuntimeCircuitBreaker,
  RuntimeGuardError,
  RuntimeIntelligence,
  RuntimeTelemetry,
  createRuntimeIntelligence,
  defaultTraceIdProvider,
  runGuardChain,
  useRuntimeIntelligence,
} from './RuntimeIntelligence';

export { runtimeIntelligence as coreRuntimeIntelligence } from './RuntimeIntelligence';

export type {
  FullPipelineBridge,
  Guard,
  GuardChainConfig,
  RuntimeCircuitBreakerDefaults,
  RuntimeCircuitBreakerSnapshot,
  RuntimeCircuitBreakerState,
  RuntimeContext,
  RuntimeDecision,
  RuntimeDecisionAlternative,
  RuntimeDecisionExplanation,
  RuntimeGuardExecutionOptions,
  RuntimeGuardResult,
  RuntimeHealthSnapshot,
  RuntimeIntelligenceConfig,
  RuntimeLearningInfluence,
  RuntimeTelemetryConfig,
  RuntimeTelemetrySnapshot,
  TelemetryEvent,
  TraceId,
  TraceIdProvider,
  UseRuntimeIntelligenceOptions,
} from './RuntimeIntelligence';

export {
  assertRuntimeRepoSnapshotReady,
  clearRuntimeRepoSnapshot,
  clearRuntimeRepoSnapshotResult,
  createRuntimeMemoryStorage,
  createRuntimeRepoSnapshot,
  getRuntimeRepoSnapshotHealth,
  getRuntimeRepoSnapshotReadyGate,
  hasRuntimeRepoSnapshot,
  inspectRuntimeRepoSnapshotStorage,
  loadRuntimeRepoSnapshot,
  saveRuntimeRepoSnapshot,
  validateDurableRepoSnapshot,
  validateLoadedRuntimeRepoSnapshot,
  validateRuntimeRepoSnapshotInput,
} from './repoSnapshotRuntime';

export type {
  DurableRepoSnapshot,
  DurableRepoSnapshotValidationReport,
  RuntimeRepoFileSnapshot,
  RuntimeRepoFileType,
  RuntimeRepoSnapshotInput,
  RuntimeRepoSnapshotReadyGate,
  RuntimeRepoSnapshotResult,
  RuntimeRepoSnapshotStorageStatus,
} from './repoSnapshotRuntime';

export * as RuntimeIntelligenceCore from './RuntimeIntelligence';
export * as RuntimeRepoSnapshotRuntime from './repoSnapshotRuntime';

const REPO_SNAPSHOT_RUNTIME_METHODS = {
  createRepoSnapshot: createRuntimeRepoSnapshot,
  saveRepoSnapshot: saveRuntimeRepoSnapshot,
  loadRepoSnapshot: loadRuntimeRepoSnapshot,
  clearRepoSnapshot: clearRuntimeRepoSnapshot,
} as const;

export type RuntimeRepoSnapshotMethods = typeof REPO_SNAPSHOT_RUNTIME_METHODS;

export type RuntimeIntelligenceWithRepoSnapshot = ReturnType<
  typeof createBaseRuntimeIntelligence
> &
  RuntimeRepoSnapshotMethods;

export function attachRepoSnapshotRuntime<TTarget extends object>(
  target: TTarget,
): TTarget & RuntimeRepoSnapshotMethods {
  return Object.assign(target, REPO_SNAPSHOT_RUNTIME_METHODS);
}

export function createRuntimeIntelligenceWithRepoSnapshot(
  config?: RuntimeIntelligenceConfig,
): RuntimeIntelligenceWithRepoSnapshot {
  return attachRepoSnapshotRuntime(createBaseRuntimeIntelligence(config));
}

export const runtimeIntelligence: RuntimeIntelligenceWithRepoSnapshot =
  attachRepoSnapshotRuntime(baseRuntimeIntelligence);

export default runtimeIntelligence;
