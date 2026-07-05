import type { RepoFile } from '../../github/types';
import type { SovereignHealthReport } from './sovereignHealth';
import type { SovereignImplementationPackage } from './sovereignRuntime';
import { maskSecrets } from '../../../shared/utils/crypto';
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

function canUseWindow(): boolean {
  return typeof window !== 'undefined' && typeof window.dispatchEvent === 'function';
}

function feedbackLamp(status: PublishGateResult['status']): 'green' | 'yellow' | 'red' {
  if (status === 'red') return 'red';
  if (status === 'idle' || status === 'warning') return 'yellow';
  return 'green';
}

function feedbackAction(result: PublishGateResult): string {
  if (result.recommendations.length > 0) return result.recommendations[0];
  if (result.allowed) return 'Continue with review.';
  return 'Open Health and Telemetry.';
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

export function publishRuntimeFeedback(result: PublishGateResult, nowMs = Date.now()): void {
  if (!canUseWindow()) return;

  // ✅ SECURITY: Mask secrets in feedback messages before publishing.
  // Health gate and publish messages may contain sensitive info from external providers.
  window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
    detail: {
      lamp: feedbackLamp(result.status),
      title: maskSecrets(result.allowed ? 'Runtime ready' : 'Runtime needs attention'),
      message: maskSecrets(result.reason),
      action: maskSecrets(feedbackAction(result)),
      thinking: false,
      source: 'runtime',
      updatedAt: nowMs,
    },
  }));
}

export function assertCanPublishPackage(
  pkg: SovereignImplementationPackage,
  ctx: PublishGateContext,
): void {
  const result = evaluateCanPublishPackage(pkg, ctx);
  if (!result.allowed) {
    publishRuntimeFeedback(result);
    throw new Error(result.reason);
  }
}

export function canPublishPackage(
  pkg: SovereignImplementationPackage,
  ctx: PublishGateContext,
): PublishGateResult {
  return evaluateCanPublishPackage(pkg, ctx);
}
