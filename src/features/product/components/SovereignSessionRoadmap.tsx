/**
 * Sovereign Session Roadmap
 *
 * Compact sidebar/line showing:
 * - Current step in plan
 * - Plan progress (steps completed)
 * - Blocker status
 * - Next allowed action
 *
 * Rule: No percentage progress. Only step count.
 *
 * @module SovereignSessionRoadmap
 */

import React from 'react';
import type { SovereignExecutionSession } from '../runtime/sovereignExecutionSessionRuntime';
import type { SovereignPlan, SovereignPlanStep } from '../runtime/sovereignPlanRuntime';
import type { SovereignSessionHealth } from '../runtime/sovereignRuntimeIntelligenceIntegration';

/**
 * Progress indicator for plan
 */
export interface SovereignPlanProgress {
  readonly completed: number;
  readonly blocked: number;
  readonly total: number;
  readonly currentStepId: string | null;
  readonly nextStepId: string | null;
}

/**
 * Main roadmap component
 */
export interface SovereignSessionRoadmapProps {
  readonly session: SovereignExecutionSession | null;
  readonly progress: SovereignPlanProgress;
  readonly health: SovereignSessionHealth;
  readonly nextAllowedAction?: string;
  readonly compact?: boolean;
}

/**
 * Renders a single step in the roadmap
 */
const RoadmapStep: React.FC<{
  step: SovereignPlanStep;
  isCurrent: boolean;
  isNext: boolean;
}> = ({ step, isCurrent, isNext }) => {
  const getStatusIcon = () => {
    if (step.status === 'completed') return '✓';
    if (step.status === 'blocked') return '⚠';
    if (isCurrent) return '▶';
    if (isNext) return '○';
    return '·';
  };

  const getStatusColor = () => {
    if (step.status === 'completed') return '#22c55e';
    if (step.status === 'blocked') return '#f59e0b';
    if (isCurrent) return '#3b82f6';
    return '#888';
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '4px 0',
        opacity: step.status === 'completed' ? 0.6 : 1,
      }}
    >
      <span style={{ color: getStatusColor(), fontWeight: isCurrent ? 600 : 400 }}>
        {getStatusIcon()}
      </span>
      <span
        style={{
          fontSize: '12px',
          color: isCurrent ? '#333' : '#666',
          fontWeight: isCurrent ? 500 : 400,
          maxWidth: '150px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={step.title}
      >
        {step.title}
      </span>
    </div>
  );
};

/**
 * Compact single-line roadmap for sidebar
 */
export const SovereignSessionRoadmap: React.FC<SovereignSessionRoadmapProps> = ({
  session,
  progress,
  health,
  nextAllowedAction,
  compact = false,
}) => {
  if (!session || !session.plan) {
    return (
      <div
        data-testid="roadmap-empty"
        style={{
          padding: '8px 12px',
          fontSize: '12px',
          color: '#888',
          fontStyle: 'italic',
        }}
      >
        Keine aktive Session
      </div>
    );
  }

  const { plan } = session;
  const { completed, blocked, total } = progress;

  if (compact) {
    // Single line compact view
    const healthIcon = health === 'healthy' ? '✓' : health === 'warning' ? '⚠' : '✗';
    const currentStep = plan.steps.find((s) => s.id === progress.currentStepId);
    const currentTitle = currentStep?.title ?? 'N/A';

    return (
      <div
        data-testid="roadmap-compact"
        style={{
          padding: '4px 12px',
          fontSize: '11px',
          color: '#666',
          display: 'flex',
          gap: '8px',
          alignItems: 'center',
        }}
      >
        <span>{healthIcon}</span>
        <span>{completed}/{total}</span>
        <span style={{ color: '#888' }}>·</span>
        <span
          title={currentTitle}
          style={{ maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis' }}
        >
          {currentTitle}
        </span>
        {blocked > 0 && (
          <>
            <span style={{ color: '#888' }}>·</span>
            <span style={{ color: '#f59e0b' }}>{blocked} blockiert</span>
          </>
        )}
      </div>
    );
  }

  // Full view with step list
  return (
    <div
      data-testid="roadmap-full"
      style={{
        padding: '12px',
        backgroundColor: 'rgba(0,0,0,0.03)',
        borderRadius: '8px',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '12px',
          paddingBottom: '8px',
          borderBottom: '1px solid rgba(0,0,0,0.1)',
        }}
      >
        <div style={{ fontWeight: 600, fontSize: '13px' }}>
          📋 {plan.title}
        </div>
        <div style={{ fontSize: '12px', color: '#666' }}>
          {completed}/{total}
        </div>
      </div>

      {/* Steps */}
      <div style={{ marginBottom: '12px' }}>
        {plan.steps.map((step) => (
          <RoadmapStep
            key={step.id}
            step={step}
            isCurrent={step.id === progress.currentStepId}
            isNext={step.id === progress.nextStepId}
          />
        ))}
      </div>

      {/* Next allowed action */}
      {nextAllowedAction && (
        <div
          style={{
            padding: '6px 8px',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            borderRadius: '4px',
            fontSize: '11px',
            color: '#3b82f6',
          }}
        >
          → {nextAllowedAction}
        </div>
      )}

      {/* Blocker warning */}
      {blocked > 0 && (
        <div
          style={{
            marginTop: '8px',
            padding: '6px 8px',
            backgroundColor: 'rgba(245, 158, 11, 0.1)',
            borderRadius: '4px',
            fontSize: '11px',
            color: '#f59e0b',
          }}
        >
          ⚠️ {blocked} Schritt{blocked > 1 ? 'e' : ''} blockiert
        </div>
      )}
    </div>
  );
};

/**
 * Extracts progress from session
 */
export function extractPlanProgress(session: SovereignExecutionSession | null): SovereignPlanProgress | null {
  if (!session?.plan) return null;

  const { plan, currentStepId } = session;
  const steps = plan.steps;

  const completed = steps.filter((s) => s.status === 'completed').length;
  const blocked = steps.filter((s) => s.status === 'blocked').length;
  const total = steps.length;

  // Find next uncompleted step
  const nextStepId = steps.find(
    (s) => s.status !== 'completed' && s.id !== currentStepId,
  )?.id ?? null;

  return {
    completed,
    blocked,
    total,
    currentStepId,
    nextStepId,
  };
}

/**
 * Formats next allowed action for display
 */
export function formatNextAllowedAction(action: SovereignPlanProgress['nextStepId'] | null): string | undefined {
  if (!action) return undefined;

  // Map step IDs to human-readable actions
  const actionMap: Record<string, string> = {
    'resolve_blocker': 'Blocker lösen',
    'continue': 'Fortsetzen',
    'finish': 'Abschließen',
    'retry': 'Erneut versuchen',
  };

  return actionMap[action] ?? `Nächster: ${action}`;
}
