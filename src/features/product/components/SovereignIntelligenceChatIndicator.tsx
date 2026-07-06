/**
 * Sovereign Intelligence Chat Indicator
 *
 * Compact, non-intrusive intelligence feedback in chat.
 * Shows learning-based hints without fake success claims.
 *
 * Rule: Never display percentage progress or raw tokens.
 *
 * @module SovereignIntelligenceChatIndicator
 */

import React from 'react';
import type { SovereignSessionHealth } from '../runtime/sovereignRuntimeIntelligenceIntegration';

export interface SovereignIntelligenceChatIndicatorProps {
  readonly health: SovereignSessionHealth;
  readonly healthReason: string;
  readonly recommendations: readonly string[];
  readonly lastToolName?: string;
  readonly blockerCount?: number;
  readonly compact?: boolean;
}

/**
 * Formats a single recommendation for chat display
 */
function formatRecommendation(rec: string, index: number): string {
  const icons: Record<string, string> = {
    'Strategie überprüfen': '🔄',
    'Strategie wechseln': '🔀',
    'Fehler analysieren': '🔍',
    'Alternative Strategie wählen': '💡',
    'Ähnliche Sessions analysieren': '📊',
    'Fehlende Voraussetzungen identifizieren': '⚠️',
  };
  return `${icons[rec] ?? '•'} ${rec}`;
}

/**
 * Compact chat indicator for intelligence feedback.
 * Appears as a single line in the chat stream.
 */
export const SovereignIntelligenceChatIndicator: React.FC<SovereignIntelligenceChatIndicatorProps> = ({
  health,
  healthReason,
  recommendations,
  lastToolName,
  blockerCount = 0,
  compact = false,
}) => {
  if (compact) {
    // Single line compact view
    const healthIcon = health === 'healthy' ? '✅' : health === 'warning' ? '⚠️' : '🚫';
    return (
      <div
        data-testid="intelligence-indicator-compact"
        style={{
          padding: '4px 12px',
          fontSize: '13px',
          color: health === 'healthy' ? '#22c55e' : health === 'warning' ? '#f59e0b' : '#ef4444',
          fontStyle: 'italic',
        }}
      >
        {healthIcon} {healthReason}
        {blockerCount > 0 && ` (${blockerCount}x)`}
      </div>
    );
  }

  // Full view with recommendations
  const healthIcon = health === 'healthy' ? '✅' : health === 'warning' ? '⚠️' : '🚫';
  const borderColor = health === 'healthy' ? '#22c55e' : health === 'warning' ? '#f59e0b' : '#ef4444';

  return (
    <div
      data-testid="intelligence-indicator"
      style={{
        padding: '12px 16px',
        borderLeft: `3px solid ${borderColor}`,
        backgroundColor: 'rgba(0,0,0,0.05)',
        margin: '8px 0',
        fontSize: '13px',
      }}
    >
      {/* Header */}
      <div style={{ fontWeight: 600, marginBottom: '4px' }}>
        {healthIcon} Intelligence Feedback
      </div>

      {/* Reason */}
      <div style={{ color: '#666', marginBottom: recommendations.length > 0 ? '8px' : 0 }}>
        {healthReason}
      </div>

      {/* Last tool info */}
      {lastToolName && (
        <div style={{ color: '#888', fontSize: '12px', marginBottom: '4px' }}>
          Letztes Tool: {lastToolName}
        </div>
      )}

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div style={{ marginTop: '8px' }}>
          {recommendations.map((rec, i) => (
            <div key={i} style={{ padding: '2px 0' }}>
              {formatRecommendation(rec, i)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/**
 * Tool success hint for chat.
 * Shows historical success without fake percentage.
 */
export interface SovereignToolSuccessHintProps {
  readonly toolName: string;
  readonly hasHistory: boolean;
  readonly wasSuccessful?: boolean;
}

export const SovereignToolSuccessHint: React.FC<SovereignToolSuccessHintProps> = ({
  toolName,
  hasHistory,
  wasSuccessful,
}) => {
  if (!hasHistory) {
    return (
      <div
        data-testid="tool-hint-first-use"
        style={{
          padding: '4px 12px',
          fontSize: '12px',
          color: '#888',
          fontStyle: 'italic',
        }}
      >
        🤖 Erster Einsatz von {toolName}
      </div>
    );
  }

  const icon = wasSuccessful ? '✅' : '⚠️';
  const text = wasSuccessful
    ? `${toolName} war in früheren Sessions erfolgreich`
    : `${toolName} hatte früher Probleme`;

  return (
    <div
      data-testid="tool-hint-history"
      style={{
        padding: '4px 12px',
        fontSize: '12px',
        color: wasSuccessful ? '#22c55e' : '#f59e0b',
        fontStyle: 'italic',
      }}
    >
      {icon} {text}
    </div>
  );
};

/**
 * Blocker warning for chat.
 */
export interface SovereignBlockerWarningProps {
  readonly blocker: string;
  readonly occurrenceCount: number;
}

export const SovereignBlockerWarning: React.FC<SovereignBlockerWarningProps> = ({
  blocker,
  occurrenceCount,
}) => {
  return (
    <div
      data-testid="blocker-warning"
      style={{
        padding: '4px 12px',
        fontSize: '12px',
        color: '#ef4444',
        fontStyle: 'italic',
      }}
    >
      ⚠️ Blocker wiederholt ({occurrenceCount}x): {blocker}
      {occurrenceCount > 2 && ' → Strategie-Wechsel empfohlen'}
    </div>
  );
};

/**
 * Strategy change hint for chat.
 */
export interface SovereignStrategyChangeHintProps {
  readonly fromStrategy: string;
  readonly toStrategy: string;
}

export const SovereignStrategyChangeHint: React.FC<SovereignStrategyChangeHintProps> = ({
  fromStrategy,
  toStrategy,
}) => {
  return (
    <div
      data-testid="strategy-change-hint"
      style={{
        padding: '4px 12px',
        fontSize: '12px',
        color: '#3b82f6',
        fontStyle: 'italic',
      }}
    >
      🔀 Strategie-Wechsel: {fromStrategy} → {toStrategy}
    </div>
  );
};
