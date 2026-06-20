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
  if (result.allowed) return 'Continue with guarded runtime output.';
  return 'Open Health and Telemetry before continuing.';
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

  const lamp = feedbackLamp(result.status);
  const title = result.allowed ? 'Runtime output ready' : 'Runtime output needs attention';
  const action = feedbackAction(result);
  const detail = {
    lamp,
    title,
    message: result.reason,
    action,
    thinking: false,
    source: 'runtime',
    updatedAt: nowMs,
  };

  window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', { detail }));
  window.dispatchEvent(new CustomEvent('sovereign:dependency-telemetry-event', {
    detail: {
      stage: 'ui',
      level: result.allowed ? 'success' : result.status === 'red' ? 'error' : 'warning',
      label: result.allowed ? 'runtime-output:allowed' : 'runtime-output:attention-needed',
      message: result.reason,
      details: {
        dependencySource: 'runtime',
        status: result.status,
        recommendations: result.recommendations.length,
      },
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
