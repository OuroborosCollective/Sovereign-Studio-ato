/**
 * Publish Runtime Telemetry Feedback Helper
 * 
 * Provides a clean, testable interface for publishing Health-Gate feedback
 * to the Coach without going through the error path.
 */

import { maskSecrets } from '../../../shared/utils/crypto';
import type { PublishGateResult } from './appPublishRuntime';

export type TelemetryFeedbackLamp = 'green' | 'yellow' | 'red';
export type TelemetryFeedbackSource = 'runtime' | 'telemetry' | 'health-gate';

export interface TelemetryFeedback {
  lamp: TelemetryFeedbackLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source: TelemetryFeedbackSource;
  updatedAt: number;
}

function canUseWindow(): boolean {
  return typeof window !== 'undefined' && typeof window.dispatchEvent === 'function';
}

function mapStatusToLamp(status: PublishGateResult['status']): TelemetryFeedbackLamp {
  if (status === 'red') return 'red';
  if (status === 'idle' || status === 'warning') return 'yellow';
  return 'green';
}

function deriveAction(result: PublishGateResult): string {
  if (result.recommendations.length > 0) return result.recommendations[0];
  if (result.allowed) return 'Continue with review.';
  return 'Open Health and Telemetry.';
}

export function createTelemetryFeedback(result: PublishGateResult, nowMs = Date.now()): TelemetryFeedback {
  // ✅ SECURITY: Proactively mask secrets in telemetry feedback.
  return {
    lamp: mapStatusToLamp(result.status),
    title: maskSecrets(result.allowed ? 'Runtime ready' : 'Runtime needs attention'),
    message: maskSecrets(result.reason),
    action: maskSecrets(deriveAction(result)),
    thinking: false,
    source: 'health-gate',
    updatedAt: nowMs,
  };
}

export function publishRuntimeTelemetryFeedback(result: PublishGateResult, nowMs = Date.now()): void {
  if (!canUseWindow()) return;

  const feedback = createTelemetryFeedback(result, nowMs);

  window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
    detail: feedback,
  }));
}

export function createHealthGateTelemetryEvent(
  result: PublishGateResult,
  metadata?: Record<string, unknown>
): TelemetryFeedback & { metadata?: Record<string, unknown> } {
  const feedback = createTelemetryFeedback(result);
  return {
    ...feedback,
    metadata,
  };
}
