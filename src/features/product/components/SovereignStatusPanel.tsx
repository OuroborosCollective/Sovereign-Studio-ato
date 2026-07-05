/**
 * SovereignStatusPanel
 *
 * Displays honest runtime status with separated blocker counts.
 * Follows Issue #504 requirements:
 * - Top counters distinguish Errors, Warnings, Active Blockers
 * - Repeated same blockers are deduplicated
 * - Next Action matches actual state
 * - GitHub ready stays ready even if OpenHands missing
 * - No global "bereit" when write route is blocked
 * - UI shows only Runtime state
 */

import React from 'react';
import { C } from './builderConstants';
import { deriveBlockerNextAction } from '../runtime/sovereignBlockerRegistry';
import type { GitHubAccessState } from '../runtime/githubAccessRuntime';

export interface SovereignStatusPanelProps {
  /** GitHub access state */
  githubState: GitHubAccessState;
  /** Whether executor (OpenHands) is available */
  executorAvailable: boolean;
  /** Whether OpenHands is configured */
  openhandsConfigured: boolean;
  /** Whether patch route is available */
  patchRouteAvailable: boolean;
  /** Whether repo is ready (from runtime state) */
  repoReady: boolean;
  /** Custom blocker counts from action stream */
  blockerCounts?: {
    activeBlockers: number;
    warnings: number;
    errors: number;
  };
  /** Custom next action (if not derived) */
  customNextAction?: string;
  /** Whether to show compact view */
  compact?: boolean;
}

/**
 * Get display color for status
 */
function statusColor(hasErrors: boolean, hasWarnings: boolean, hasBlockers: boolean): string {
  if (hasErrors) return C.rose;
  if (hasWarnings || hasBlockers) return C.amber;
  return C.green;
}

/**
 * Individual status indicator chip
 */
function StatusChip({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: string;
}) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 12,
        background: `${color}15`,
        border: `1px solid ${color}40`,
        fontSize: 11,
        fontFamily: 'monospace',
        color,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: color,
          flexShrink: 0,
        }}
      />
      {count > 0 ? `${count}` : '0'} {label}
    </span>
  );
}

/**
 * Sub-status item (e.g., "Repo bereit", "Patch-Route blockiert")
 */
function SubStatus({
  label,
  ready,
}: {
  label: string;
  ready: boolean;
}) {
  const color = ready ? C.green : C.rose;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 10,
        fontFamily: 'monospace',
        color: ready ? C.text : C.textSub,
      }}
    >
      <span
        style={{
          width: 5,
          height: 5,
          borderRadius: '50%',
          background: color,
          flexShrink: 0,
        }}
      />
      {label}
    </span>
  );
}

/**
 * SovereignStatusPanel
 *
 * Shows honest runtime status without fake green states.
 * Displays separated counts for errors, warnings, and active blockers.
 */
export function SovereignStatusPanel({
  githubState,
  executorAvailable,
  openhandsConfigured,
  patchRouteAvailable,
  repoReady,
  blockerCounts,
  customNextAction,
  compact = false,
}: SovereignStatusPanelProps) {
  // Derive next action based on runtime state
  const nextAction =
    customNextAction ??
    deriveBlockerNextAction({
      githubReady: githubState === 'ready',
      githubValidating: githubState === 'validating',
      executorAvailable,
      patchRouteAvailable,
      openhandsConfigured,
    });

  const hasErrors = (blockerCounts?.errors ?? 0) > 0;
  const hasWarnings = (blockerCounts?.warnings ?? 0) > 0;
  const hasBlockers = (blockerCounts?.activeBlockers ?? 0) > 0;
  const mainColor = statusColor(hasErrors, hasWarnings, hasBlockers);

  // Determine overall readiness based on sub-components (from runtime state)
  const githubReady = githubState === 'ready';
  const patchReady = patchRouteAvailable;
  const draftPrMissing = !githubReady || !patchReady;

  if (compact) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '4px 12px',
          background: `${mainColor}10`,
          borderRadius: 8,
          fontSize: 11,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: mainColor,
            flexShrink: 0,
            boxShadow: hasBlockers || hasWarnings || hasErrors ? `0 0 4px ${mainColor}` : 'none',
          }}
        />
        <span style={{ color: C.text, fontFamily: 'monospace' }}>
          {blockerCounts ? `${blockerCounts.activeBlockers} Blocker · ${blockerCounts.warnings} Warnungen · ${blockerCounts.errors} Fehler` : nextAction}
        </span>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        padding: 12,
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
      }}
    >
      {/* Status chips row */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <StatusChip
          label="Blocker"
          count={blockerCounts?.activeBlockers ?? 0}
          color={C.amber}
        />
        <StatusChip
          label="Warnungen"
          count={blockerCounts?.warnings ?? 0}
          color={C.amber}
        />
        <StatusChip
          label="Fehler"
          count={blockerCounts?.errors ?? 0}
          color={C.rose}
        />
      </div>

      {/* Sub-status indicators */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <SubStatus label="Repo bereit" ready={repoReady} />
        <SubStatus label="GitHub bereit" ready={githubReady} />
        <SubStatus label="Patch-Route" ready={patchReady} />
        <SubStatus label="Draft PR" ready={!draftPrMissing} />
      </div>

      {/* Next action */}
      <div
        style={{
          padding: '6px 10px',
          background: `${mainColor}08`,
          borderRadius: 6,
          borderLeft: `3px solid ${mainColor}`,
        }}
      >
        <span
          style={{
            fontSize: 10,
            color: C.textMuted,
            fontFamily: 'monospace',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          Nächste Aktion
        </span>
        <p
          style={{
            margin: '2px 0 0',
            fontSize: 12,
            color: C.text,
            fontFamily: 'monospace',
          }}
        >
          {nextAction}
        </p>
      </div>
    </div>
  );
}
