/**
 * WorkerBlockerCard - Visible worker recovery state with explicit Retry and Diagnose actions
 * 
 * Shows degraded/blocked state when WorkerRuntimeBlocker is present.
 * OpenHands action is gated behind real code/Draft-PR intent.
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
  onRetry: () => void;
  onExplain: () => void;
  onOpenHandsInstead?: (message: string) => void;
  /** Used to gate OpenHands action behind real code intent */
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
  onExplain,
  onOpenHandsInstead,
  userMessage,
}) => {
  const { diagnostic, health } = blocker;
  const canOpenHands = userMessage && hasCodeIntent(userMessage);
  
  const handleOpenHands = useCallback(() => {
    if (canOpenHands && onOpenHandsInstead) {
      onOpenHandsInstead(userMessage);
    }
  }, [canOpenHands, onOpenHandsInstead, userMessage]);

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
          onClick={onRetry}
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            background: C.rose + '20',
            border: `1px solid ${C.rose}40`,
            color: C.rose,
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
          }}
          aria-label="Retry Worker request"
        >
          Retry
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
        
        {canOpenHands && onOpenHandsInstead && (
          <button
            type="button"
            onClick={handleOpenHands}
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
            aria-label="Use OpenHands for code task instead"
          >
            OpenHands für Code-Auftrag
          </button>
        )}
      </div>
    </div>
  );
};

// Degraded banner for TopBar
export interface WorkerDegradedBannerProps {
  blocker: {
    readonly message: string;
    readonly diagnostic: DevChatWorkerDiagnostic;
    readonly health?: DevChatWorkerHealthResult;
    readonly createdAt: number;
  };
  onRetry: () => void;
}

export const WorkerDegradedBanner: React.FC<WorkerDegradedBannerProps> = ({
  blocker,
  onRetry,
}) => {
  const scope = formatScope(blocker.diagnostic);
  
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="worker-degraded-banner"
      onClick={onRetry}
      style={{
        padding: '6px 16px',
        background: C.rose + '20',
        borderBottom: `1px solid ${C.rose}40`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        cursor: 'pointer',
        fontSize: 12,
        color: C.rose,
      }}
    >
      <span>Worker offline</span>
      <span style={{ color: C.textSub }}>·</span>
      <span>scope={scope}</span>
      <span style={{ color: C.textSub }}>·</span>
      <span>Retry ↩</span>
    </div>
  );
};

export default WorkerBlockerCard;
