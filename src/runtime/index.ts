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

import { decideSovereignInternalOperator } from './sovereignInternalOperatorRuntime';

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

export { decideSovereignInternalOperator } from './sovereignInternalOperatorRuntime';

export type {
  SovereignInternalOperatorDecision,
  SovereignInternalOperatorInput,
  SovereignInternalOperatorNode,
  SovereignInternalOperatorRoute,
  SovereignInternalOperatorSignal,
  SovereignInternalOperatorStage,
} from './sovereignInternalOperatorRuntime';

export * as RuntimeIntelligenceCore from './RuntimeIntelligence';
export * as RuntimeRepoSnapshotRuntime from './repoSnapshotRuntime';
export * as SovereignInternalOperatorRuntime from './sovereignInternalOperatorRuntime';

const REPO_SNAPSHOT_RUNTIME_METHODS = {
  createRepoSnapshot: createRuntimeRepoSnapshot,
  saveRepoSnapshot: saveRuntimeRepoSnapshot,
  loadRepoSnapshot: loadRuntimeRepoSnapshot,
  clearRepoSnapshot: clearRuntimeRepoSnapshot,
} as const;

const SOVEREIGN_INTERNAL_OPERATOR_RUNTIME_METHODS = {
  decideSovereignInternalOperator,
} as const;

export type RuntimeRepoSnapshotMethods = typeof REPO_SNAPSHOT_RUNTIME_METHODS;
export type SovereignInternalOperatorRuntimeMethods = typeof SOVEREIGN_INTERNAL_OPERATOR_RUNTIME_METHODS;

export type RuntimeIntelligenceWithRepoSnapshot = ReturnType<
  typeof createBaseRuntimeIntelligence
> &
  RuntimeRepoSnapshotMethods &
  SovereignInternalOperatorRuntimeMethods;

export function attachRepoSnapshotRuntime<TTarget extends object>(
  target: TTarget,
): TTarget & RuntimeRepoSnapshotMethods & SovereignInternalOperatorRuntimeMethods {
  return Object.assign(
    target,
    REPO_SNAPSHOT_RUNTIME_METHODS,
    SOVEREIGN_INTERNAL_OPERATOR_RUNTIME_METHODS,
  );
}

export function createRuntimeIntelligenceWithRepoSnapshot(
  config?: RuntimeIntelligenceConfig,
): RuntimeIntelligenceWithRepoSnapshot {
  return attachRepoSnapshotRuntime(createBaseRuntimeIntelligence(config));
}

export const runtimeIntelligence: RuntimeIntelligenceWithRepoSnapshot =
  attachRepoSnapshotRuntime(baseRuntimeIntelligence);

export default runtimeIntelligence;
