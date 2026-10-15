/**
 * AgentWorkTimeline - Compact, collapsible work timeline for agent tasks.
 *
 * Displays only real runtime state from AgentWorkSnapshot.
 * No fake progress, no percentage bars, no invented states.
 */

import React, { useState } from 'react';
import type { AgentWorkSnapshot, AgentWorkState, AgentWorkEvent } from '../runtime/agentWorkRuntime';
import { isTerminalState, isActiveState, labelForState } from '../runtime/agentWorkRuntime';

type TimelineTone = 'verified' | 'active' | 'warning' | 'error' | 'idle';

function toneForState(state: AgentWorkState): TimelineTone {
  if (state === 'draft_pr_ready') return 'verified';
  if (state === 'failed' || state === 'blocked') return 'error';
  if (isActiveState(state)) return 'active';
  if (state === 'idle') return 'idle';
  return 'warning';
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
  const tone = toneForState(event.state);
  return (
    <li className={`sovereign-timeline-event sovereign-timeline-event--${tone}${isCurrent ? ' sovereign-timeline-event--current' : ''}`}>
      <span className="sovereign-timeline-event__icon" aria-hidden="true">
        {iconForState(event.state)}
      </span>
      <div className="sovereign-timeline-event__body">
        <span className="sovereign-timeline-event__label">{event.label}</span>
        {event.detail && (
          <span className="sovereign-timeline-event__detail" title={event.detail}>
            {event.detail}
          </span>
        )}
      </div>
    </li>
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
  className,
}) => {
  const [expanded, setExpanded] = useState(false);

  const { state, events, repoFullName, jobId, branchName, commitSha, draftPrUrl, blockerReason } = snapshot;
  const isTerminal = isTerminalState(state);
  const isActive = isActiveState(state);
  const tone = toneForState(state);
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
    <section
      role="region"
      aria-label="Agent Work Timeline"
      aria-busy={isActive}
      data-testid="agent-work-timeline"
      className={`sovereign-instrument-panel sovereign-runtime-timeline sovereign-runtime-timeline--${tone}${className ? ` ${className}` : ''}`}
    >
      <div className="sovereign-runtime-timeline__header">
        <span className={`sovereign-runtime-timeline__status sovereign-runtime-timeline__status--${tone}`} aria-hidden="true" />
        <span className="sovereign-runtime-timeline__title">{headerLabel}</span>
        {repoFullName && (
          <span className="sovereign-runtime-timeline__repo" title={repoFullName}>
            {repoFullName}
          </span>
        )}
      </div>

      <div className={`sovereign-runtime-timeline__state sovereign-runtime-timeline__state--${tone}`} aria-live="polite">
        <span>{stateLabel}</span>
        {jobId && state !== 'draft_pr_ready' && (
          <span className="sovereign-runtime-timeline__job" title={`Job ID: ${jobId}`}>
            Job: {jobId}
          </span>
        )}
      </div>

      {events.length > 0 && (
        <div className="sovereign-runtime-timeline__events">
          {hiddenCount > 0 && (
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="sovereign-timeline-toggle focus-visible:ring-2 focus-visible:ring-[var(--sovereign-focus-ring)] focus-visible:outline-none"
              title={`${hiddenCount} ältere Ereignisse anzeigen`}
              aria-label={`${hiddenCount} ältere Ereignisse anzeigen`}
              aria-expanded={expanded}
              aria-controls="agent-work-events"
            >
              ↑ {hiddenCount} ältere Ereignisse
            </button>
          )}
          <ul
            id="agent-work-events"
            role="list"
            aria-label="Ereignisprotokoll"
            className="sovereign-runtime-timeline__list"
          >
            {visibleEvents.map((event, idx) => (
              <EventRow
                key={event.id}
                event={event}
                isCurrent={idx === visibleEvents.length - 1}
              />
            ))}
          </ul>
          {expanded && events.length > COLLAPSE_THRESHOLD && (
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="sovereign-timeline-toggle focus-visible:ring-2 focus-visible:ring-[var(--sovereign-focus-ring)] focus-visible:outline-none"
              title="Weniger Ereignisse anzeigen"
              aria-label="Weniger Ereignisse anzeigen"
              aria-expanded={expanded}
              aria-controls="agent-work-events"
            >
              ↓ Weniger anzeigen
            </button>
          )}
        </div>
      )}

      {branchName && (
        <div className="sovereign-runtime-timeline__metadata">
          <span>Branch</span>
          <span className="sovereign-runtime-timeline__value" title={branchName}>{branchName}</span>
          {commitSha && (
            <>
              <span aria-hidden="true">·</span>
              <span>Commit</span>
              <span className="sovereign-runtime-timeline__value" title={`Commit SHA: ${commitSha}`}>{commitSha.slice(0, 7)}</span>
            </>
          )}
        </div>
      )}

      {blockerReason && (
        <div className="sovereign-runtime-timeline__blocker" role="alert">
          <span className="sovereign-runtime-timeline__blocker-label">BLOCKED</span>
          <span>{blockerReason}</span>
        </div>
      )}

      {state === 'draft_pr_ready' && draftPrUrl && (
        <div className="sovereign-runtime-timeline__actions">
          {onOpenPr && (
            <button
              type="button"
              onClick={onOpenPr}
              className="sovereign-timeline-action sovereign-timeline-action--verified focus-visible:ring-2 focus-visible:ring-[var(--sovereign-focus-ring)] focus-visible:outline-none"
              title="Draft PR auf GitHub öffnen"
            >
              PR öffnen
            </button>
          )}
          {onViewDiff && (
            <button
              type="button"
              onClick={onViewDiff}
              className="sovereign-timeline-action sovereign-timeline-action--active focus-visible:ring-2 focus-visible:ring-[var(--sovereign-focus-ring)] focus-visible:outline-none"
              title="Diff-Vorschau der Änderungen anzeigen"
            >
              Diff ansehen
            </button>
          )}
        </div>
      )}

      {isTerminal && !draftPrUrl && state !== 'draft_pr_ready' && (
        <div className="sovereign-runtime-timeline__empty">
          Kein PR wurde erstellt.
        </div>
      )}
    </section>
  );
};

export default AgentWorkTimeline;
