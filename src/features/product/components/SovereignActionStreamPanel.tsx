/**
 * SovereignActionStreamPanel
 *
 * Renders the live runtime action log as a chat-bubble in the message feed.
 * All LLM routes on the Sovereign Revolver (worker, code-llm, openhands, free-chat, …)
 * are equal citizens here — every route contributes events, none is privileged.
 *
 * Hard rules:
 *  - Runtime creates truth; this component only displays it.
 *  - No fake events, no percentage progress, no auto-success lamps.
 *  - Collapsed by default: compact header + last-event summary.
 *  - Expanded on tap: chronological event list up to maxEvents.
 */

import React, { useState } from 'react';
import {
  describeSovereignActionEvent,
  type SovereignActionEvent,
  type SovereignActionEventState,
  type SovereignActionStreamState,
} from '../runtime/sovereignActionStreamRuntime';
import { C } from './builderConstants';

// ─── constants ───────────────────────────────────────────────────────────────

const STATE_LABEL: Record<SovereignActionEventState, string> = {
  queued:     'wartet',
  running:    'läuft',
  blocked:    'blockiert',
  done:       'fertig',
  failed:     'fehlgeschlagen',
};

const STATE_COLOR: Record<SovereignActionEventState, string> = {
  queued:  C.amber,
  running: C.sky,
  blocked: C.rose,
  done:    C.green,
  failed:  C.rose,
};

// ─── helpers ─────────────────────────────────────────────────────────────────

function formatTime(value: number): string {
  try {
    return new Date(value).toLocaleTimeString('de-DE', {
      hour:   '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '';
  }
}

function workerTitle(stream: SovereignActionStreamState): string {
  if (stream.activeRoute) return `Sovereign arbeitet · ${stream.activeRoute} läuft`;
  const state = stream.lastEvent?.state;
  if (state === 'blocked') return 'Sovereign wartet auf nächsten echten Schritt';
  if (state === 'failed')  return 'Sovereign hat einen Blocker gefunden';
  return 'Sovereign hat den Arbeitsschritt protokolliert';
}

function dotStyle(stream: SovereignActionStreamState): { color: string; glow: boolean } {
  if (stream.activeRoute) return { color: C.sky, glow: true };
  const state = stream.lastEvent?.state;
  if (state === 'blocked' || state === 'failed') return { color: C.rose, glow: false };
  if (state === 'done')                          return { color: C.green, glow: false };
  return { color: C.textSub, glow: false };
}

// ─── sub-components ──────────────────────────────────────────────────────────

function EventRow({ event }: { event: SovereignActionEvent }) {
  const color = STATE_COLOR[event.state];
  return (
    <article
      data-route={event.route}
      data-state={event.state}
      style={{
        display:       'grid',
        gridTemplateColumns: '8px 1fr',
        alignItems:    'start',
        gap:           7,
        padding:       '5px 0',
        borderBottom:  `1px solid ${C.border}22`,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width:      8,
          height:     8,
          marginTop:  4,
          borderRadius: '50%',
          background: color,
          flexShrink: 0,
          boxShadow:  event.state === 'running' ? `0 0 5px ${color}` : 'none',
        }}
      />
      <span style={{ minWidth: 0 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
          <span
            style={{
              flex:       1,
              fontFamily: 'monospace',
              fontSize:   10,
              color:      C.text,
              wordBreak:  'break-word',
            }}
          >
            {event.label}
          </span>
          <span
            style={{
              border:       `1px solid ${color}44`,
              color,
              borderRadius: 999,
              padding:      '1px 5px',
              fontFamily:   'monospace',
              fontSize:     7.5,
              whiteSpace:   'nowrap',
            }}
          >
            {event.route} · {STATE_LABEL[event.state]}
          </span>
        </span>
        {event.detail ? (
          <span
            style={{
              display:    'block',
              marginTop:  2,
              fontSize:   11,
              color:      C.textSub,
              lineHeight: 1.35,
            }}
          >
            {event.detail}
          </span>
        ) : (
          <span className="sr-only">{describeSovereignActionEvent(event)}</span>
        )}
        <span
          style={{
            display:    'block',
            marginTop:  2,
            fontFamily: 'monospace',
            fontSize:   8,
            color:      C.textMuted,
          }}
        >
          {formatTime(event.createdAt)}
        </span>
      </span>
    </article>
  );
}

// ─── main component ──────────────────────────────────────────────────────────

export function SovereignActionStreamPanel({
  stream,
  maxEvents = 10,
}: {
  readonly stream: SovereignActionStreamState;
  readonly maxEvents?: number;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!stream.events.length) return null;

  const events    = stream.events.slice(-Math.max(1, maxEvents));
  const lastEvent = stream.lastEvent;
  const dot       = dotStyle(stream);
  const title     = workerTitle(stream);

  return (
    <div
      aria-label="Sovereign Action Stream"
      role="log"
      data-testid="sovereign-action-stream"
      data-layout="chat-worker-bubble"
      style={{ display: 'flex', alignItems: 'flex-end', gap: 8, padding: '2px 12px' }}
    >
      {/* Avatar */}
      <div
        aria-hidden="true"
        style={{
          width:       30,
          height:      30,
          borderRadius: 10,
          flexShrink:  0,
          background:  C.surface,
          border:      `1px solid ${C.border}`,
          display:     'flex',
          alignItems:  'center',
          justifyContent: 'center',
          fontSize:    13,
          color:       C.textSub,
          marginBottom: 2,
        }}
      >
        ⬡
      </div>

      {/* Bubble */}
      <section
        style={{
          maxWidth:     '82%',
          width:        '100%',
          padding:      '10px 12px',
          borderRadius: '4px 18px 18px 18px',
          border:       `1px solid ${C.border}`,
          background:   (C as Record<string, string>).asstBg ?? C.surface,
          boxShadow:    '0 1px 4px rgba(0,0,0,0.3)',
        }}
      >
        {/* ── Header ──────────────────────────────── */}
        <div
          style={{
            display:     'flex',
            alignItems:  'center',
            gap:         8,
            marginBottom: expanded ? 8 : 0,
          }}
        >
          {/* Status dot */}
          <span
            aria-hidden="true"
            style={{
              width:      7,
              height:     7,
              borderRadius: '50%',
              background: dot.color,
              flexShrink: 0,
              boxShadow:  dot.glow ? `0 0 6px ${dot.color}` : 'none',
            }}
          />

          {/* Title + last-event summary when collapsed */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontFamily: 'monospace',
                fontSize:   10,
                color:      C.textSub,
                fontWeight: 700,
              }}
            >
              {title}
            </div>
            {!expanded && lastEvent && (
              <div
                style={{
                  fontFamily: 'monospace',
                  fontSize:   8.5,
                  color:      C.textMuted,
                  marginTop:  1,
                }}
              >
                {lastEvent.label} · {STATE_LABEL[lastEvent.state]}
              </div>
            )}
          </div>

          {/* Expand / collapse toggle */}
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls="sovereign-action-stream-events"
            onClick={() => setExpanded((v) => !v)}
            style={{
              padding:      '2px 8px',
              borderRadius: 6,
              background:   'transparent',
              border:       `1px solid ${C.border}`,
              color:        C.textSub,
              fontSize:     9,
              fontFamily:   'monospace',
              cursor:       'pointer',
              whiteSpace:   'nowrap',
              flexShrink:   0,
            }}
          >
            {expanded ? 'Details ausblenden' : 'Details'}
          </button>
        </div>

        {/* ── Expanded event list ──────────────────── */}
        {expanded && (
          <div
            id="sovereign-action-stream-events"
            style={{ display: 'grid', gap: 0 }}
          >
            {events.map((event) => (
              <EventRow key={`${event.id}:${event.createdAt}`} event={event} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
