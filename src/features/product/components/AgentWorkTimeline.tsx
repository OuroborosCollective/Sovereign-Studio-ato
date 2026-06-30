/**
 * AgentWorkTimeline - Compact, collapsible work timeline for agent tasks.
 *
 * Displays only real runtime state from AgentWorkSnapshot.
 * No fake progress, no percentage bars, no invented states.
 */

import React, { useState } from 'react';
import type { AgentWorkSnapshot, AgentWorkState, AgentWorkEvent } from '../runtime/agentWorkRuntime';
import { isTerminalState, isActiveState, labelForState } from '../runtime/agentWorkRuntime';

const C = {
  bg:       '#0e1116',
  surface:  '#161c24',
  border:   '#232d3a',
  accent:   '#00d9b1',
  text:     '#cdd9e5',
  textSub:  '#768390',
  green:    '#34d399',
  amber:    '#fbbf24',
  rose:     '#fb7185',
  sky:      '#22d3ee',
} as const;

function lampForState(state: AgentWorkState): string {
  if (state === 'draft_pr_ready') return C.green;
  if (state === 'failed' || state === 'blocked') return C.rose;
  if (isActiveState(state)) return C.sky;
  if (state === 'idle') return C.textSub;
  return C.amber;
}

function iconForState(state: AgentWorkState): string {
  if (state === 'draft_pr_ready') return '✓';
  if (state === 'failed') return '✗';
  if (state === 'blocked') return '⊘';
  if (isActiveState(state)) return '→';
  if (state === 'idle') return '○';
  return '✓';
}

interface EventRowProps {
  event: AgentWorkEvent;
  isCurrent: boolean;
}

const EventRow: React.FC<EventRowProps> = ({ event, isCurrent }) => {
  const color = lampForState(event.state);
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: '3px 0',
        opacity: isCurrent ? 1 : 0.7,
      }}
    >
      <span
        style={{
          width: 16,
          textAlign: 'center',
          fontSize: 11,
          color,
          flexShrink: 0,
          marginTop: 1,
        }}
      >
        {iconForState(event.state)}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 12, color: isCurrent ? C.text : C.textSub, fontWeight: isCurrent ? 500 : 400 }}>
          {event.label}
        </span>
        {event.detail && (
          <span
            style={{
              fontSize: 11,
              color: C.textSub,
              marginLeft: 6,
              fontFamily: 'monospace',
              wordBreak: 'break-all',
            }}
          >
            {event.detail}
          </span>
        )}
      </div>
    </div>
  );
};

export interface AgentWorkTimelineProps {
  snapshot: AgentWorkSnapshot;
  onOpenPr?: () => void;
  onViewDiff?: () => void;
  className?: string;
}

export const AgentWorkTimeline: React.FC<AgentWorkTimelineProps> = ({
  snapshot,
  onOpenPr,
  onViewDiff,
}) => {
  const [expanded, setExpanded] = useState(false);

  const { state, events, repoFullName, jobId, branchName, commitSha, draftPrUrl, blockerReason } = snapshot;
  const isTerminal = isTerminalState(state);
  const isActive = isActiveState(state);
  const lamp = lampForState(state);
  const stateLabel = labelForState(state);

  const COLLAPSE_THRESHOLD = 4;
  const visibleEvents = expanded ? events : events.slice(-COLLAPSE_THRESHOLD);
  const hiddenCount = events.length - visibleEvents.length;

  const headerLabel = (() => {
    if (state === 'draft_pr_ready') return 'Draft PR bereit';
    if (state === 'failed' || state === 'blocked') return 'Sovereign blockiert';
    if (isActive) return 'Sovereign arbeitet';
    return 'Sovereign';
  })();

  return (
    <div
      role="region"
      aria-label="Agent Work Timeline"
      data-testid="agent-work-timeline"
      style={{
        margin: '8px 0',
        padding: '12px 14px',
        borderRadius: 12,
        background: C.surface,
        border: `1px solid ${lamp}30`,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        maxWidth: 393,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: lamp,
            flexShrink: 0,
            boxShadow: isActive ? `0 0 6px ${lamp}` : undefined,
          }}
        />
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text, flex: 1 }}>
          {headerLabel}
        </span>
        {repoFullName && (
          <span style={{ fontSize: 11, color: C.textSub, fontFamily: 'monospace' }}>
            {repoFullName}
          </span>
        )}
      </div>

      <div style={{ fontSize: 11, color: lamp, fontWeight: 500 }}>
        {stateLabel}
        {jobId && state !== 'draft_pr_ready' && (
          <span style={{ color: C.textSub, fontWeight: 400, marginLeft: 8, fontFamily: 'monospace' }}>
            Job: {jobId}
          </span>
        )}
      </div>

      {events.length > 0 && (
        <div
          style={{
            borderTop: `1px solid ${C.border}`,
            paddingTop: 8,
            display: 'flex',
            flexDirection: 'column',
            gap: 0,
          }}
        >
          {hiddenCount > 0 && (
            <button
              type="button"
              onClick={() => setExpanded(true)}
              style={{
                background: 'none',
                border: 'none',
                padding: '2px 0 6px 0',
                cursor: 'pointer',
                color: C.textSub,
                fontSize: 11,
                textAlign: 'left',
              }}
              aria-label={`${hiddenCount} ältere Ereignisse anzeigen`}
            >
              ↑ {hiddenCount} ältere Ereignisse
            </button>
          )}
          {visibleEvents.map((event, idx) => (
            <EventRow
              key={event.id}
              event={event}
              isCurrent={idx === visibleEvents.length - 1}
            />
          ))}
          {expanded && events.length > COLLAPSE_THRESHOLD && (
            <button
              type="button"
              onClick={() => setExpanded(false)}
              style={{
                background: 'none',
                border: 'none',
                padding: '4px 0 0 0',
                cursor: 'pointer',
                color: C.textSub,
                fontSize: 11,
                textAlign: 'left',
              }}
            >
              ↓ Weniger anzeigen
            </button>
          )}
        </div>
      )}

      {branchName && (
        <div style={{ fontSize: 11, color: C.textSub, fontFamily: 'monospace' }}>
          Branch: <span style={{ color: C.sky }}>{branchName}</span>
          {commitSha && (
            <>
              {' · '}Commit: <span style={{ color: C.sky }}>{commitSha.slice(0, 7)}</span>
            </>
          )}
        </div>
      )}

      {blockerReason && (
        <div
          style={{
            fontSize: 12,
            color: C.rose,
            background: `${C.rose}10`,
            borderRadius: 6,
            padding: '6px 10px',
          }}
        >
          {blockerReason}
        </div>
      )}

      {state === 'draft_pr_ready' && draftPrUrl && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', borderTop: `1px solid ${C.border}`, paddingTop: 8 }}>
          {onOpenPr && (
            <button
              type="button"
              onClick={onOpenPr}
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
              aria-label="PR öffnen"
            >
              PR öffnen
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
            >
              Diff ansehen
            </button>
          )}
        </div>
      )}

      {isTerminal && !draftPrUrl && state !== 'draft_pr_ready' && (
        <div style={{ fontSize: 11, color: C.textSub, borderTop: `1px solid ${C.border}`, paddingTop: 8 }}>
          Kein PR wurde erstellt.
        </div>
      )}
    </div>
  );
};

export default AgentWorkTimeline;
