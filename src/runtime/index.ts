/**
 * Runtime Intelligence Library
 *
 * Unified public exports for the runtime intelligence system.
 *
 * This file is the stable handoff surface for app/runtime integration.
 * It exposes:
 * - Core runtime intelligence
 * - Augmented runtime intelligence with repo snapshot helpers
 * - Runtime health / telemetry / guard / circuit breaker types
 * - Namespaced internal access for system-level modules
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

// ============================================================================
// Core Runtime Exports
// ============================================================================

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

export {
  runtimeIntelligence as coreRuntimeIntelligence,
} from './RuntimeIntelligence';

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

// ============================================================================
// Repo Snapshot Runtime Exports
// ============================================================================

export {
  clearRuntimeRepoSnapshot,
  createRuntimeRepoSnapshot,
  loadRuntimeRepoSnapshot,
  saveRuntimeRepoSnapshot,
} from './repoSnapshotRuntime';

export type {
  RuntimeRepoSnapshotInput,
  RuntimeRepoSnapshotResult,
} from './repoSnapshotRuntime';

// ============================================================================
// Namespaced System Access
// ============================================================================

export * as RuntimeIntelligenceCore from './RuntimeIntelligence';
export * as RuntimeRepoSnapshotRuntime from './repoSnapshotRuntime';

// ============================================================================
// Augmented Runtime Surface
// ============================================================================

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

/**
 * Attaches repo snapshot runtime helpers to any runtime-like target.
 *
 * This is intentionally explicit: the repo snapshot helpers are public sidecar
 * runtime methods, not hidden truth-path mutations.
 */
export function attachRepoSnapshotRuntime<TTarget extends object>(
  target: TTarget,
): TTarget & RuntimeRepoSnapshotMethods {
  return Object.assign(target, REPO_SNAPSHOT_RUNTIME_METHODS);
}

/**
 * Creates a fresh RuntimeIntelligence instance with repo snapshot helpers attached.
 *
 * Useful for tests, isolated workbenches, mobile operator flows, or runtime sandboxes
 * that must not share singleton telemetry / circuit breaker state.
 */
export function createRuntimeIntelligenceWithRepoSnapshot(
  config?: RuntimeIntelligenceConfig,
): RuntimeIntelligenceWithRepoSnapshot {
  return attachRepoSnapshotRuntime(createBaseRuntimeIntelligence(config));
}

/**
 * Default public singleton instance with repo snapshot runtime methods attached.
 *
 * Public API:
 * - runtimeIntelligence.decide(...)
 * - runtimeIntelligence.withGuard(...)
 * - runtimeIntelligence.getRuntimeHealth()
 * - runtimeIntelligence.saveRepoSnapshot(...)
 * - runtimeIntelligence.loadRepoSnapshot(...)
 */
export const runtimeIntelligence: RuntimeIntelligenceWithRepoSnapshot =
  attachRepoSnapshotRuntime(baseRuntimeIntelligence);

export default runtimeIntelligence;
