/**
 * WorkerBlockerCard - Visible worker recovery state with explicit Retry and Diagnose actions
 * 
 * Shows degraded/blocked state when WorkerRuntimeBlocker is present.
 * Sovereign Agent action is gated behind real code/Draft-PR intent.
 */

import React, { useCallback } from 'react';
import type { DevChatWorkerDiagnostic, DevChatWorkerHealthResult } from '../runtime/devChatWorkerBridge';

export interface WorkerBlockerCardProps {
  blocker: {
    readonly message: string;
    readonly diagnostic: DevChatWorkerDiagnostic;
    readonly health?: DevChatWorkerHealthResult;
    readonly createdAt: number;
  };
  onRetry?: () => void;
  /** Retry with a specific message - cleaner runtime action path */
  onRetryWithMessage?: (message: string) => void;
  onExplain: () => void;
  onAgentInstead?: (message: string) => void;
  /** Used to gate Sovereign Agent action behind real code intent */
  userMessage?: string;
}

const C = {
  bg:        '#0e1116',
  surface:   '#161c24',
  border:    '#232d3a',
  rose:      '#fb7185',
  amber:     '#fbbf24',
  text:      '#cdd9e5',
  textSub:   '#768390',
  green:     '#34d399',
  sky:       '#22d3ee',
} as const;

const DIAGNOSTIC_MESSAGE_MARKERS = [
  'worker nicht erreichbar',
  'worker offline',
  'worker-call nicht blind',
  'ich wiederhole den kaputten',
  'scope:',
  'scope=',
  'health:',
  'route:',
  'antwortauszug:',
  'diagnose',
  'http 500',
  'failed to fetch',
];

function normalizeActionMessage(message: string | undefined): string | undefined {
  const trimmed = message?.trim();
  if (!trimmed) return undefined;

  const lower = trimmed.toLowerCase();
  if (DIAGNOSTIC_MESSAGE_MARKERS.some((marker) => lower.includes(marker))) {
    return undefined;
  }

  return trimmed;
}

// Check if message contains real code/Draft-PR intent
function hasCodeIntent(message: string): boolean {
  const codeSignals = [
    'code', 'fix', 'bug', 'feature', 'implement', 'refactor',
    'pr', 'pull request', 'draft', 'publish', 'build', 'test',
    'function', 'class', 'component', 'api', 'error', 'exception',
    '//', 'import', 'export', 'const ', 'function ', 'async ',
    'erstelle', 'baue', 'generiere', 'paket', 'pr ',
  ];
  const lower = message.toLowerCase();
  return codeSignals.some(signal => lower.includes(signal));
}

function formatScope(diagnostic: DevChatWorkerDiagnostic): string {
  // Use type-safe scope checks
  const scope = diagnostic.scope;
  if (scope === 'network') return 'network';
  if (scope === 'client_request') return 'client';
  if (scope === 'worker_config') return 'config';
  if (scope === 'worker_runtime') return 'runtime';
  if (scope === 'upstream_provider') return 'upstream';
  return 'unknown';
}

function formatHealth(health: DevChatWorkerHealthResult | undefined): string {
  if (!health) return 'Health: loading…';
  
  const parts: string[] = [];
  if (health.secretConfigured !== undefined) parts.push(`secret=${health.secretConfigured ? 'ok' : 'fail'}`);
  if (health.upstreamConfigured !== undefined) parts.push(`upstream=${health.upstreamConfigured ? 'ok' : 'fail'}`);
  if (health.model) parts.push(`model=${health.model}`);
  
  return parts.length > 0 ? `Health: ${parts.join(' · ')}` : 'Health: unknown';
}

export const WorkerBlockerCard: React.FC<WorkerBlockerCardProps> = ({
  blocker,
  onRetry,
  onRetryWithMessage,
  onExplain,
  onAgentInstead,
  userMessage,
}) => {
  const { diagnostic, health } = blocker;
  const actionMessage = normalizeActionMessage(userMessage);
  const canAgent = Boolean(actionMessage && hasCodeIntent(actionMessage));
  const canRetry = Boolean((onRetryWithMessage && actionMessage) || onRetry);
  
  // A visible retry action is enabled only when a real retry callback exists.
  const handleRetry = useCallback(() => {
    if (onRetryWithMessage && actionMessage) {
      onRetryWithMessage(actionMessage);
      return;
    }
    onRetry?.();
  }, [onRetryWithMessage, onRetry, actionMessage]);
  
  const handleAgent = useCallback(() => {
    if (canAgent && actionMessage && onAgentInstead) {
      onAgentInstead(actionMessage);
    }
  }, [canAgent, onAgentInstead, actionMessage]);

  return (
    <div
      role="alert"
      aria-live="polite"
      data-testid="worker-blocker-card"
      style={{
        margin: '8px 16px',
        padding: '16px',
        borderRadius: 12,
        background: C.surface,
        border: `1px solid ${C.rose}40`,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontSize: 18, lineHeight: 1 }}>⚠️</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, color: C.rose, fontSize: 14 }}>
            Worker nicht erreichbar
          </div>
          <div style={{ fontSize: 12, color: C.textSub, marginTop: 4 }}>
            Scope: {formatScope(diagnostic)}
            {diagnostic.status && ` · HTTP ${diagnostic.status}`}
            {diagnostic.statusText && ` (${diagnostic.statusText})`}
          </div>
        </div>
      </div>

      {/* Health info */}
      <div style={{ fontSize: 11, color: C.textSub, fontFamily: 'monospace' }}>
        {formatHealth(health)}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <button
          type="button"
          onClick={handleRetry}
          disabled={!canRetry}
          aria-disabled={!canRetry}
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            background: C.rose + '20',
            border: `1px solid ${C.rose}40`,
            color: C.rose,
            fontSize: 13,
            fontWeight: 500,
            cursor: canRetry ? 'pointer' : 'not-allowed',
            opacity: canRetry ? 1 : 0.55,
          }}
          aria-label={canRetry ? 'Retry Worker request' : 'Retry unavailable: no previous worker request'}
        >
          {canRetry ? 'Retry' : 'Retry nicht verfügbar'}
        </button>
        
        <button
          type="button"
          onClick={onExplain}
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            background: C.amber + '15',
            border: `1px solid ${C.amber}30`,
            color: C.amber,
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
          }}
          aria-label="Explain diagnostic"
        >
          Diagnose erklären
        </button>
        
        {canAgent && onAgentInstead && (
          <button
            type="button"
            onClick={handleAgent}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              background: C.sky + '15',
              border: `1px solid ${C.sky}30`,
              color: C.sky,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
            }}
            aria-label="Use Sovereign Agent for code task instead"
          >
            Sovereign Agent für Code-Auftrag
          </button>
        )}
      </div>
    </div>
  );
};

// Degraded banner for TopBar

export default WorkerBlockerCard;

export interface WorkerDegradedBannerProps {
  blocker: {
    readonly message: string;
    readonly diagnostic: DevChatWorkerDiagnostic;
    readonly health?: DevChatWorkerHealthResult;
    readonly createdAt: number;
  };
  /** Legacy callback - clears blocker only */
  onRetry?: () => void;
  /** Real retry callback - triggers actual runtime retry */
  onRetryWithMessage?: (message: string) => void;
  /** Last user message to retry */
  userMessage?: string;
}

export const WorkerDegradedBanner: React.FC<WorkerDegradedBannerProps> = ({
  blocker,
  onRetry,
  onRetryWithMessage,
  userMessage,
}) => {
  const scope = formatScope(blocker.diagnostic);
  const actionMessage = normalizeActionMessage(userMessage);
  const canRetry = Boolean((onRetryWithMessage && actionMessage) || onRetry);

  const handleClick = useCallback(() => {
    if (onRetryWithMessage && actionMessage) {
      onRetryWithMessage(actionMessage);
    } else if (onRetry) {
      onRetry();
    }
  }, [onRetry, onRetryWithMessage, actionMessage]);

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="worker-degraded-banner"
      onClick={canRetry ? handleClick : undefined}
      aria-disabled={!canRetry}
      style={{
        padding: '6px 16px',
        background: C.rose + '20',
        borderBottom: `1px solid ${C.rose}40`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        cursor: canRetry ? 'pointer' : 'default',
        opacity: canRetry ? 1 : 0.75,
        fontSize: 12,
        color: C.rose,
      }}
    >
      <span>Worker offline</span>
      <span style={{ color: C.textSub }}>·</span>
      <span>scope={scope}</span>
      <span style={{ color: C.textSub }}>·</span>
      <span>{canRetry ? 'Retry' : 'Kein Retry-Request'}</span>
    </div>
  );
};
