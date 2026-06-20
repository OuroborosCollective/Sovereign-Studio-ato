import type { RepoFile } from '../../github/types';
import type { SovereignHealthReport } from './sovereignHealth';
import type { SovereignImplementationPackage } from './sovereignRuntime';
import { assertSovereignHealthAllowsRuntimeOutput } from './sovereignFunctionalGuards';

export interface PublishGateContext {
  repoFiles: RepoFile[];
  healthReport: SovereignHealthReport;
}

export interface PublishGateResult {
  allowed: boolean;
  blockedReason?: string;
}

/**
 * Health gate: blocks publish when system health is red/idle.
 * Use this as part of the publish guard chain.
 */
export function assertCanPublishPackage(
  pkg: SovereignImplementationPackage,
  ctx: PublishGateContext
): void {
  // Health gate - system must not be red/idle
  assertSovereignHealthAllowsRuntimeOutput(ctx.healthReport);
}

/**
 * Non-throwing version that returns validation result.
 */
export function canPublishPackage(
  pkg: SovereignImplementationPackage,
  ctx: PublishGateContext
): PublishGateResult {
  try {
    assertCanPublishPackage(pkg, ctx);
    return { allowed: true };
  } catch (error) {
    return {
      allowed: false,
      blockedReason: error instanceof Error ? error.message : String(error),
    };
  }
}
