import type { RepoFile } from '../../github/types';
import type { SovereignHealthReport } from './sovereignHealth';
import type { SovereignImplementationPackage } from './sovereignRuntime';
import { getSovereignHealthRuntimeGate, type SovereignHealthRuntimeGate } from './sovereignFunctionalGuards';

export interface PublishGateContext {
  repoFiles: RepoFile[];
  healthReport: SovereignHealthReport;
}

export interface PublishGateResult {
  allowed: boolean;
  status: SovereignHealthReport['status'];
  reason: string;
  recommendations: string[];
  blockedReason?: string;
}

const MAX_RECOMMENDATIONS = 3;

function compactRecommendations(items: string[]): string[] {
  return items.map((item) => item.trim()).filter(Boolean).slice(0, MAX_RECOMMENDATIONS);
}

export function formatPublishGateMessage(gate: SovereignHealthRuntimeGate): string {
  const recommendations = compactRecommendations(gate.warnings);
  if (!recommendations.length) return gate.reason;
  return `${gate.reason} Next: ${recommendations.join(' | ')}`;
}

export function evaluateCanPublishPackage(
  pkg: SovereignImplementationPackage,
  ctx: PublishGateContext,
): PublishGateResult {
  void pkg;
  const gate = getSovereignHealthRuntimeGate(ctx.healthReport);
  const reason = formatPublishGateMessage(gate);

  return {
    allowed: gate.allowed,
    status: gate.status,
    reason,
    recommendations: compactRecommendations(gate.warnings),
    blockedReason: gate.allowed ? undefined : reason,
  };
}

export function assertCanPublishPackage(
  pkg: SovereignImplementationPackage,
  ctx: PublishGateContext,
): void {
  const result = evaluateCanPublishPackage(pkg, ctx);
  if (!result.allowed) throw new Error(result.reason);
}

export function canPublishPackage(
  pkg: SovereignImplementationPackage,
  ctx: PublishGateContext,
): PublishGateResult {
  return evaluateCanPublishPackage(pkg, ctx);
}
