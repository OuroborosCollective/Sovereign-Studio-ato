/**
 * AgentResultCard - Real result card shown only when runtime-backed data exists.
 *
 * Rule: If draftPrUrl is absent, no success card appears.
 * Every field shown is sourced from AgentWorkSnapshot, never invented.
 */

import React from 'react';
import type { AgentWorkSnapshot } from '../runtime/agentWorkRuntime';

const C = {
  surface:  '#161c24',
  border:   '#232d3a',
  accent:   '#00d9b1',
  text:     '#cdd9e5',
  textSub:  '#768390',
  green:    '#34d399',
  sky:      '#22d3ee',
  amber:    '#fbbf24',
  rose:     '#fb7185',
} as const;

export type ChecksState = 'running' | 'green' | 'red' | 'unknown';

export interface AgentResultCardProps {
  snapshot: AgentWorkSnapshot;
  checksState?: ChecksState;
  onOpen?: () => void;
  onViewDiff?: () => void;
  onWatchChecks?: () => void;
}

function checksColor(state: ChecksState): string {
  if (state === 'green') return C.green;
  if (state === 'red') return C.rose;
  if (state === 'running') return C.sky;
  return C.textSub;
}

function checksLabel(state: ChecksState): string {
  if (state === 'green') return 'Checks grün';
  if (state === 'red') return 'Checks rot';
  if (state === 'running') return 'Checks laufen…';
  return 'Checks unbekannt';
}

function extractPrNumber(url: string): string | null {
  const match = url.match(/\/pull\/(\d+)$/);
  return match ? `#${match[1]}` : null;
}

export const AgentResultCard: React.FC<AgentResultCardProps> = ({
  snapshot,
  checksState = 'unknown',
  onOpen,
  onViewDiff,
  onWatchChecks,
}) => {
  const { state, draftPrUrl, branchName, commitSha, repoFullName } = snapshot;

  if (state !== 'draft_pr_ready' || !draftPrUrl) {
    return null;
  }

  const prNumber = extractPrNumber(draftPrUrl);
  const color = checksColor(checksState);

  return (
    <div
      role="region"
      aria-label="Agent Ergebnis"
      title="Agent Ergebnis"
      data-testid="agent-result-card"
      style={{
        margin: '8px 0',
        padding: '14px 16px',
        borderRadius: 12,
        background: C.surface,
        border: `1px solid ${C.green}40`,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        maxWidth: 393,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: C.green,
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: 13, fontWeight: 600, color: C.green }}>
          Ergebnis bereit
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: C.textSub, width: 52, flexShrink: 0 }}>Typ</span>
          <span style={{ fontSize: 12, color: C.text }}>Draft PR</span>
        </div>
        {prNumber && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: C.textSub, width: 52, flexShrink: 0 }}>PR</span>
            <span style={{ fontSize: 12, color: C.sky, fontFamily: 'monospace' }}>{prNumber}</span>
          </div>
        )}
        {repoFullName && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: C.textSub, width: 52, flexShrink: 0 }}>Repo</span>
            <span style={{ fontSize: 12, color: C.text, fontFamily: 'monospace' }}>{repoFullName}</span>
          </div>
        )}
        {branchName && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: C.textSub, width: 52, flexShrink: 0 }}>Branch</span>
            <span
              style={{
                fontSize: 12,
                color: C.sky,
                fontFamily: 'monospace',
                wordBreak: 'break-all',
              }}
            >
              {branchName}
            </span>
          </div>
        )}
        {commitSha && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: C.textSub, width: 52, flexShrink: 0 }}>Commit</span>
            <span style={{ fontSize: 12, color: C.sky, fontFamily: 'monospace' }}>
              {commitSha.slice(0, 7)}
            </span>
          </div>
        )}
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: C.textSub, width: 52, flexShrink: 0 }}>Checks</span>
          <span style={{ fontSize: 12, color, fontFamily: 'monospace' }}>
            {checksLabel(checksState)}
          </span>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          gap: 8,
          flexWrap: 'wrap',
          borderTop: `1px solid ${C.border}`,
          paddingTop: 10,
        }}
      >
        {onOpen && (
          <button
            type="button"
            onClick={onOpen}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              background: `${C.green}20`,
              border: `1px solid ${C.green}40`,
              color: C.green,
              fontSize: 12,
              fontWeight: 500,
              cursor: 'pointer',
            }}
            aria-label="Öffnen"
            title="Öffnen"
          >
            Öffnen
          </button>
        )}
        {onViewDiff && (
          <button
            type="button"
            onClick={onViewDiff}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              background: `${C.sky}15`,
              border: `1px solid ${C.sky}30`,
              color: C.sky,
              fontSize: 12,
              fontWeight: 500,
              cursor: 'pointer',
            }}
            aria-label="Diff ansehen"
            title="Diff ansehen"
          >
            Diff ansehen
          </button>
        )}
        {onWatchChecks && checksState === 'running' && (
          <button
            type="button"
            onClick={onWatchChecks}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              background: `${C.amber}15`,
              border: `1px solid ${C.amber}30`,
              color: C.amber,
              fontSize: 12,
              fontWeight: 500,
              cursor: 'pointer',
            }}
            aria-label="Checks beobachten"
            title="Checks beobachten"
          >
            Checks beobachten
          </button>
        )}
      </div>
    </div>
  );
};

export default AgentResultCard;
