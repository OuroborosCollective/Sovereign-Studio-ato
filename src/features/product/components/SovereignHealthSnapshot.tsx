/**
 * Sovereign Health Snapshot Widget
 *
 * Compact footer widget showing Intelligence layer health.
 * Single line, non-intrusive display.
 *
 * Rule: No percentage progress. Only binary health state.
 *
 * @module SovereignHealthSnapshot
 */

import React from 'react';
import type { SovereignIntelligenceStats } from '../runtime/sovereignRuntimeIntelligenceIntegration';

export interface SovereignHealthSnapshotProps {
  readonly stats: SovereignIntelligenceStats;
  readonly showDetails?: boolean;
}

/**
 * Health icons for different states
 */
function getHealthIcon(active: boolean, avgConfidence: number): string {
  if (!active) return '⚪';
  if (avgConfidence >= 0.7) return '🟢';
  if (avgConfidence >= 0.4) return '🟡';
  return '🔴';
}

/**
 * Formats a number compactly (e.g., 1000 -> 1K)
 */
function formatCompact(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return value.toString();
}

/**
 * Compact health snapshot for footer display.
 * Single line showing key metrics.
 */
export const SovereignHealthSnapshot: React.FC<SovereignHealthSnapshotProps> = ({
  stats,
  showDetails = false,
}) => {
  const { predictive, learning } = stats;

  // Build compact display parts
  const parts: string[] = [];

  // Intelligence status
  if (predictive.active) {
    const icon = getHealthIcon(predictive.active, predictive.avgConfidence);
    parts.push(`${icon} Intel`);
  } else {
    parts.push('⚪ Intel');
  }

  // Node and pattern count
  if (predictive.nodeCount > 0) {
    parts.push(`${formatCompact(predictive.nodeCount)} Nodes`);
  }

  if (predictive.patternCount > 0) {
    parts.push(`${formatCompact(predictive.patternCount)} Patterns`);
  }

  // Learning stats
  if (learning.totalSignals > 0) {
    const rateText = learning.successRate >= 80 ? '✓' : learning.successRate >= 50 ? '~' : '!';
    parts.push(`${formatCompact(learning.totalSignals)} Sig ${rateText}`);
  }

  if (parts.length === 0) {
    return null;
  }

  if (showDetails) {
    return (
      <div
        data-testid="health-snapshot-detailed"
        style={{
          padding: '8px 16px',
          backgroundColor: 'rgba(0,0,0,0.05)',
          borderTop: '1px solid rgba(0,0,0,0.1)',
          fontSize: '12px',
          color: '#666',
          fontFamily: 'monospace',
        }}
      >
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontWeight: 600 }}>Predictive</span>
            <span style={{ marginLeft: '8px' }}>
              {predictive.active ? 'Active' : 'Inactive'}
              {predictive.nodeCount > 0 && ` • ${predictive.nodeCount} nodes`}
              {predictive.patternCount > 0 && ` • ${predictive.patternCount} patterns`}
              {predictive.avgConfidence > 0 && ` • ${(predictive.avgConfidence * 100).toFixed(0)}% conf`}
            </span>
          </div>
          <div>
            <span style={{ fontWeight: 600 }}>Learning</span>
            <span style={{ marginLeft: '8px' }}>
              {learning.totalSignals} signals
              {learning.successCount > 0 && ` • ${learning.successCount} ✓`}
              {learning.failureCount > 0 && ` • ${learning.failureCount} ✗`}
              {learning.successRate > 0 && ` • ${learning.successRate.toFixed(0)}% rate`}
            </span>
          </div>
        </div>
      </div>
    );
  }

  // Compact single-line view
  return (
    <div
      data-testid="health-snapshot-compact"
      style={{
        padding: '4px 12px',
        fontSize: '11px',
        color: '#888',
        fontFamily: 'monospace',
        display: 'flex',
        gap: '8px',
        alignItems: 'center',
      }}
    >
      {parts.join(' | ')}
    </div>
  );
};

/**
 * Minimal dot indicator for session health.
 * Use in tight spaces where full snapshot doesn't fit.
 */
export interface SovereignHealthDotProps {
  readonly health: 'healthy' | 'warning' | 'critical';
}

export const SovereignHealthDot: React.FC<SovereignHealthDotProps> = ({ health }) => {
  const color = health === 'healthy' ? '#22c55e' : health === 'warning' ? '#f59e0b' : '#ef4444';
  const title = health === 'healthy' ? 'Session healthy' : health === 'warning' ? 'Warning' : 'Critical';

  return (
    <div
      data-testid="health-dot"
      title={title}
      style={{
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: color,
        display: 'inline-block',
      }}
    />
  );
};

/**
 * Session state badge for compact display.
 */
export interface SovereignSessionBadgeProps {
  readonly status: 'idle' | 'running' | 'blocked' | 'finished' | 'error';
  readonly stepCount?: number;
  readonly blockerCount?: number;
}

export const SovereignSessionBadge: React.FC<SovereignSessionBadgeProps> = ({
  status,
  stepCount,
  blockerCount,
}) => {
  const statusConfig = {
    idle: { label: 'Idle', color: '#888' },
    running: { label: 'Active', color: '#22c55e' },
    blocked: { label: 'Blocked', color: '#f59e0b' },
    finished: { label: 'Done', color: '#3b82f6' },
    error: { label: 'Error', color: '#ef4444' },
  };

  const config = statusConfig[status];
  const parts = [config.label];
  if (stepCount !== undefined) parts.push(`${stepCount} steps`);
  if (blockerCount !== undefined && blockerCount > 0) parts.push(`${blockerCount} blockers`);

  return (
    <div
      data-testid="session-badge"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '2px 8px',
        borderRadius: '12px',
        backgroundColor: `${config.color}20`,
        color: config.color,
        fontSize: '11px',
        fontWeight: 500,
      }}
    >
      <SovereignHealthDot
        health={status === 'idle' ? 'healthy' : status === 'running' ? 'healthy' : status === 'blocked' ? 'warning' : status === 'error' ? 'critical' : 'healthy'}
      />
      {parts.join(' • ')}
    </div>
  );
};
