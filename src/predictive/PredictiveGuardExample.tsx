/**
 * Predictive Guard Integration Examples
 *
 * Demonstrates how predictive advisory signals can be shown without creating
 * fake build/publish success. These examples never execute live actions; they
 * expose callbacks so the real runtime can decide what happens next.
 *
 * @module predictive/examples
 */

import React, { useCallback, useMemo, useState } from 'react';
import { usePredictiveGuard, usePredictiveLayer } from './index';
import type { SafetyCheckResult } from './predictiveGuard';

export interface PredictiveActionExampleProps {
  onRuntimeApprovedAction?: (result: SafetyCheckResult) => Promise<void> | void;
}

type ExampleStatus = 'idle' | 'checking' | 'blocked' | 'review' | 'warning' | 'ready';

function statusFromResult(result: SafetyCheckResult): ExampleStatus {
  switch (result.suggestedAction) {
    case 'block': return 'blocked';
    case 'review': return 'review';
    case 'warn': return 'warning';
    case 'proceed':
    default:
      return 'ready';
  }
}

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) return '0%';
  return `${(Math.max(0, Math.min(1, value)) * 100).toFixed(0)}%`;
}

function AdvisoryDecisionPanel({ result }: { result: SafetyCheckResult | null }) {
  if (!result) {
    return <p className="predictive-note">Noch keine Predictive-Entscheidung. Runtime bleibt maßgeblich.</p>;
  }

  return (
    <div className={`predictive-decision ${result.riskLevel}`}>
      <div className="decision-header">
        <strong>{result.suggestedAction.toUpperCase()}</strong>
        <span>{formatPercent(result.confidence)} advisory confidence</span>
      </div>
      <p>{result.reason}</p>
      <small>Success probability: {formatPercent(result.successProbability)} · Similar patterns: {result.similarPatterns.length}</small>
    </div>
  );
}

/**
 * Build button example. It only asks the predictive guard for an advisory
 * result. The optional callback represents the real runtime handoff.
 */
export function PredictiveBuildButton({ onRuntimeApprovedAction }: PredictiveActionExampleProps) {
  const { checkSafety, isChecking } = usePredictiveGuard();
  const [status, setStatus] = useState<ExampleStatus>('idle');
  const [lastResult, setLastResult] = useState<SafetyCheckResult | null>(null);

  const handleBuildCheck = useCallback(async () => {
    setStatus('checking');
    const result = await checkSafety('build', {
      action: 'build',
      nodeId: 'runtime.container.build',
      metadata: { context: 'example-advisory-only' },
    });

    setLastResult(result);
    const nextStatus = statusFromResult(result);
    setStatus(nextStatus);

    if (nextStatus === 'ready') {
      await onRuntimeApprovedAction?.(result);
    }
  }, [checkSafety, onRuntimeApprovedAction]);

  return (
    <div className="predictive-build-button">
      <button
        onClick={handleBuildCheck}
        disabled={isChecking || status === 'checking'}
        className={`build-button ${status}`}
      >
        {isChecking || status === 'checking' ? 'Checking predictive signal…' : 'Check Build Advisory'}
      </button>
      <AdvisoryDecisionPanel result={lastResult} />
    </div>
  );
}

/**
 * Publish example. It does not publish. It only surfaces the advisory decision
 * so the real Draft-PR runtime can decide with hard guards.
 */
export function PredictivePublishButton({ onRuntimeApprovedAction }: PredictiveActionExampleProps) {
  const { checkSafety } = usePredictiveGuard();
  const [status, setStatus] = useState<ExampleStatus>('idle');
  const [lastResult, setLastResult] = useState<SafetyCheckResult | null>(null);

  const handlePublishCheck = useCallback(async () => {
    setStatus('checking');
    const result = await checkSafety('publish', {
      action: 'publish',
      nodeId: 'runtime.container.publish',
      metadata: { type: 'draft-pr', context: 'example-advisory-only' },
    });

    setLastResult(result);
    const nextStatus = statusFromResult(result);
    setStatus(nextStatus);

    if (nextStatus === 'ready') {
      await onRuntimeApprovedAction?.(result);
    }
  }, [checkSafety, onRuntimeApprovedAction]);

  return (
    <div className="predictive-publish-button">
      <button onClick={handlePublishCheck} disabled={status === 'checking'}>
        {status === 'checking' ? 'Checking predictive signal…' : 'Check Publish Advisory'}
      </button>
      <AdvisoryDecisionPanel result={lastResult} />
    </div>
  );
}

/**
 * Widget showing predictive layer advisory state. This is not a success badge.
 */
export function PredictiveHealthWidget() {
  const { snapshot, isActive, confidence, errorRate } = usePredictiveLayer();

  const status = useMemo(() => {
    if (!isActive || !snapshot) return 'inactive';
    if (errorRate > 0.2) return 'high-error';
    if (confidence < 0.3) return 'learning';
    if (confidence > 0.7) return 'advisory-clear';
    return 'monitoring';
  }, [confidence, errorRate, isActive, snapshot]);

  return (
    <div className="predictive-health-widget">
      <div className="health-header">
        <span>Predictive Layer</span>
        <span className={`status-badge ${status}`}>{status}</span>
      </div>
      <div className="health-metrics">
        <div className="metric">
          <label>Advisory confidence</label>
          <span>{formatPercent(confidence)}</span>
        </div>
        <div className="metric">
          <label>Error rate</label>
          <span>{formatPercent(errorRate)}</span>
        </div>
        <div className="metric">
          <label>Patterns</label>
          <span>{snapshot?.patternCount ?? 0}</span>
        </div>
        <div className="metric">
          <label>Synapses</label>
          <span>{snapshot?.synapseCount ?? 0}</span>
        </div>
      </div>
      <p className="predictive-note">Predictive output is advisory. Hard runtime guards decide action safety.</p>
    </div>
  );
}

/**
 * Component that shows the latest guard decision and learning counters.
 */
export function GuardDecisionLog() {
  const { stats, lastResult } = usePredictiveGuard();

  return (
    <div className="guard-log">
      <h4>Predictive Guard Decisions</h4>
      <AdvisoryDecisionPanel result={lastResult} />
      {stats && (
        <ul className="guard-stats">
          <li>Total decisions: {stats.totalDecisions}</li>
          <li>Blocked: {stats.blockedCount}</li>
          <li>Warnings: {stats.warnedCount}</li>
          <li>Accuracy: {formatPercent(stats.accuracy)}</li>
          <li>Learned actions: {stats.learnedActions}</li>
        </ul>
      )}
    </div>
  );
}

/**
 * Warning banner when predictive layer reports weak evidence.
 */
export function PredictiveWarningBanner() {
  const { snapshot, isLowConfidence, isHighErrorRate } = usePredictiveLayer();

  if (!isLowConfidence && !isHighErrorRate) return null;

  return (
    <div className={`predictive-warning ${isHighErrorRate ? 'critical' : 'warning'}`}>
      <strong>Predictive advisory</strong>
      {isHighErrorRate && <p>High error-rate signal: {formatPercent(snapshot?.errorRate ?? 0)}. Runtime verification required.</p>}
      {isLowConfidence && <p>Low confidence signal: {formatPercent(snapshot?.avgConfidence ?? 0)}. Treat as review-needed, not as failure.</p>}
    </div>
  );
}

export const PredictiveExamples = {
  PredictiveBuildButton,
  PredictivePublishButton,
  PredictiveHealthWidget,
  GuardDecisionLog,
  PredictiveWarningBanner,
};
