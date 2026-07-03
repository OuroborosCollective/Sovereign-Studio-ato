/**
 * AgentEventStream — Manus/Replit-style live action feed shown inline in the chat.
 *
 * Combines two real runtime sources:
 *  1. openhandsJob.events  — rich backend events (file edits, commands, test runs…)
 *  2. agentWorkSnapshot.events — state-machine transitions (intent → starting → running…)
 *
 * Rules:
 *  - Runtime creates truth; this component only displays it.
 *  - No fake events, no simulated progress, no percentage bars.
 *  - Newest event at bottom; auto-scroll on each new event.
 *  - Pulsing lamp only on the current (last) event when executor is active.
 */

import React, { useEffect, useRef } from "react";
import { C } from "./builderConstants";
import type { AgentWorkSnapshot, AgentWorkState } from "../runtime/agentWorkRuntime";
import type { OpenHandsJobSnapshot, OpenHandsRuntimeEvent } from "../runtime/openhandsEnterpriseRuntime";

interface StreamEvent {
  readonly id: string;
  readonly ts: number;
  readonly icon: string;
  readonly iconColor: string;
  readonly label: string;
  readonly detail?: string;
  readonly isActive: boolean;
}

export interface AgentEventStreamProps {
  readonly snapshot: AgentWorkSnapshot;
  readonly job?: OpenHandsJobSnapshot | null;
  readonly onCancel?: () => void;
  readonly onOpenDraftPr?: () => void;
  readonly onOpenFile?: (path: string) => void;
}

const ACTIVE_STATES: ReadonlySet<AgentWorkState> = new Set([
  'executor_starting', 'executor_running',
  'branch_created', 'commit_created', 'checks_running',
]);

function isExecutorActive(state: AgentWorkState): boolean {
  return ACTIVE_STATES.has(state);
}

function stateIcon(state: AgentWorkState): { icon: string; color: string } {
  if (state === 'draft_pr_ready')  return { icon: '✓', color: C.green };
  if (state === 'failed')          return { icon: '✗', color: C.rose };
  if (state === 'blocked')         return { icon: '⊘', color: C.rose };
  if (state === 'intent_detected') return { icon: '⦿', color: C.amber };
  if (state === 'executor_starting') return { icon: '↗', color: C.sky };
  if (isExecutorActive(state))     return { icon: '→', color: C.sky };
  return { icon: '·', color: C.textSub };
}

function levelIcon(level: OpenHandsRuntimeEvent['level']): { icon: string; color: string } {
  if (level === 'success') return { icon: '✓', color: C.green };
  if (level === 'error')   return { icon: '✗', color: C.rose };
  if (level === 'warning') return { icon: '⚠', color: C.amber };
  return { icon: '→', color: C.sky };
}

function buildStream(
  snapshot: AgentWorkSnapshot,
  job: OpenHandsJobSnapshot | null | undefined,
  isActive: boolean,
): StreamEvent[] {
  const events: StreamEvent[] = [];

  for (const e of snapshot.events) {
    const { icon, color } = stateIcon(e.state);
    events.push({
      id: `snap-${e.id}`,
      ts: e.ts,
      icon,
      iconColor: color,
      label: e.label,
      detail: e.detail,
      isActive: false,
    });
  }

  if (job?.events && job.events.length > 0) {
    for (const e of job.events) {
      const { icon, color } = levelIcon(e.level);
      events.push({
        id: `job-${e.at}-${e.stage}`,
        ts: e.at,
        icon,
        iconColor: color,
        label: e.message,
        detail: e.stage !== 'openhands' ? e.stage : undefined,
        isActive: false,
      });
    }
  }

  const seen = new Set<string>();
  const sorted = events
    .filter((e) => { if (seen.has(e.id)) return false; seen.add(e.id); return true; })
    .sort((a, b) => a.ts - b.ts);

  if (isActive && sorted.length > 0) {
    const last = sorted[sorted.length - 1];
    sorted[sorted.length - 1] = { ...last, isActive: true };
  }

  return sorted;
}

function formatTime(ts: number): string {
  try {
    return new Date(ts).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

function EventRow({ event }: { event: StreamEvent }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '4px 0', opacity: event.isActive ? 1 : 0.78 }}>
      <span
        style={{
          flexShrink: 0,
          width: 18,
          height: 18,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 11,
          color: event.iconColor,
          fontWeight: 700,
          marginTop: 1,
          ...(event.isActive && {
            animation: 'aes-pulse 1.2s ease-in-out infinite',
            filter: `drop-shadow(0 0 4px ${event.iconColor})`,
          }),
        }}
      >
        {event.icon}
      </span>

      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 12.5, color: event.isActive ? C.text : C.textSub, fontWeight: event.isActive ? 500 : 400, wordBreak: 'break-word' }}>
          {event.label}
        </span>
        {event.detail && (
          <span style={{ display: 'block', fontSize: 10.5, color: C.textMuted, fontFamily: 'monospace', marginTop: 1, wordBreak: 'break-all' }}>
            {event.detail}
          </span>
        )}
      </div>

      <span style={{ flexShrink: 0, fontSize: 10, color: C.textMuted, fontVariantNumeric: 'tabular-nums', alignSelf: 'flex-start', marginTop: 3 }}>
        {formatTime(event.ts)}
      </span>
    </div>
  );
}

function FileBadge({ path, onClick }: { path: string; onClick?: () => void }) {
  const name = path.split('/').pop() ?? path;
  return (
    <button
      type="button"
      title={path}
      onClick={onClick}
      style={{
        padding: '3px 8px',
        borderRadius: 5,
        background: C.surface,
        border: `1px solid ${C.border}`,
        color: C.sky,
        fontSize: 11,
        cursor: onClick ? 'pointer' : 'default',
        fontFamily: 'monospace',
        whiteSpace: 'nowrap',
        maxWidth: 160,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}
    >
      {name}
    </button>
  );
}

export function AgentEventStream({ snapshot, job, onCancel, onOpenDraftPr, onOpenFile }: AgentEventStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isActive = isExecutorActive(snapshot.state);
  const isDone = snapshot.state === 'draft_pr_ready';
  const isFailed = snapshot.state === 'failed' || snapshot.state === 'blocked';
  const changedFiles = job?.changedFiles ?? [];
  const draftPrUrl = job?.draftPrUrl ?? snapshot.draftPrUrl ?? null;

  const stream = buildStream(snapshot, job, isActive);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (typeof el.scrollTo === 'function') {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, [stream.length]);

  const headerLabel = isDone
    ? 'Draft PR bereit'
    : isFailed
      ? snapshot.state === 'blocked' ? 'Executor blockiert' : 'Executor fehlgeschlagen'
      : snapshot.state === 'executor_starting' || job?.status === 'queued'
        ? 'OpenHands startet…'
        : snapshot.state === 'intent_detected'
          ? 'Auftrag erkannt'
          : isActive || job?.status === 'running'
            ? 'OpenHands arbeitet…'
            : 'Auftrag erkannt';

  const headerColor = isDone ? C.green : isFailed ? C.rose : snapshot.state === 'intent_detected' ? C.amber : C.sky;
  const repoLabel = snapshot.repoFullName && snapshot.repoFullName !== 'unknown/repo'
    ? snapshot.repoFullName + (snapshot.branchName ? ` · ${snapshot.branchName}` : '')
    : null;

  if (stream.length === 0) return null;

  return (
    <>
      <style>{`
        @keyframes aes-pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.35; }
        }
      `}</style>

      <div role="region" aria-label="Ausführungs-Ereignisstrom" style={{ margin: '4px 16px', borderRadius: 10, background: C.surface, border: `1px solid ${C.border}`, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderBottom: `1px solid ${C.border}`, background: '#0e1116cc' }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: headerColor, flexShrink: 0, ...(isActive && { animation: 'aes-pulse 1s ease-in-out infinite', boxShadow: `0 0 6px ${headerColor}` }) }} />
          <span style={{ fontSize: 12.5, fontWeight: 600, color: headerColor, flex: 1 }}>{headerLabel}</span>
          {repoLabel && <span style={{ fontSize: 10.5, color: C.textSub, fontFamily: 'monospace' }}>{repoLabel}</span>}
          {changedFiles.length > 0 && (
            <span style={{ fontSize: 10.5, color: C.amber, background: '#fbbf2415', padding: '1px 6px', borderRadius: 4 }}>
              {changedFiles.length} Datei{changedFiles.length > 1 ? 'en' : ''}
            </span>
          )}
        </div>

        <div ref={scrollRef} style={{ padding: '8px 12px', maxHeight: 240, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 0 }}>
          {stream.map((event) => <EventRow key={event.id} event={event} />)}
        </div>

        {changedFiles.length > 0 && (
          <div style={{ padding: '6px 12px', borderTop: `1px solid ${C.border}`, display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {changedFiles.slice(0, 12).map((f) => (
              <FileBadge key={f} path={f} onClick={onOpenFile ? () => onOpenFile(f) : undefined} />
            ))}
            {changedFiles.length > 12 && <span style={{ fontSize: 11, color: C.textMuted, alignSelf: 'center' }}>+{changedFiles.length - 12} weitere</span>}
          </div>
        )}

        {(onCancel || draftPrUrl) && (
          <div style={{ padding: '8px 12px', borderTop: `1px solid ${C.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            {isActive && onCancel && (
              <button type="button" onClick={onCancel} style={{ padding: '6px 14px', borderRadius: 7, background: 'transparent', color: C.rose, fontSize: 12, fontWeight: 500, border: `1px solid ${C.rose}`, cursor: 'pointer' }}>
                Abbrechen
              </button>
            )}
            {draftPrUrl && (
              <button type="button" onClick={onOpenDraftPr ?? (() => window.open(draftPrUrl, '_blank'))} style={{ padding: '6px 14px', borderRadius: 7, background: C.green, color: '#000', fontSize: 12, fontWeight: 600, border: 'none', cursor: 'pointer' }}>
                Draft PR öffnen ↗
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}
