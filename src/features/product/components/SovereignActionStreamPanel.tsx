import React from 'react';
import {
  describeSovereignActionEvent,
  latestSovereignActionByRoute,
  type SovereignActionEvent,
  type SovereignActionEventState,
  type SovereignActionStreamState,
} from '../runtime/sovereignActionStreamRuntime';
import { C } from './builderConstants';

const STATE_LABEL: Record<SovereignActionEventState, string> = {
  queued: 'wartet',
  running: 'läuft',
  blocked: 'blockiert',
  done: 'fertig',
  failed: 'fehlgeschlagen',
};

const STATE_COLOR: Record<SovereignActionEventState, string> = {
  queued: C.amber,
  running: C.sky,
  blocked: C.amber,
  done: C.green,
  failed: C.rose,
};

function formatTime(value: number): string {
  return new Date(value).toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function eventKey(event: SovereignActionEvent): string {
  return `${event.id}:${event.createdAt}`;
}

export function SovereignActionStreamPanel({
  stream,
  maxEvents = 8,
}: {
  readonly stream: SovereignActionStreamState;
  readonly maxEvents?: number;
}) {
  const events = stream.events.slice(-Math.max(1, maxEvents));
  const latestByRoute = latestSovereignActionByRoute(stream);
  const routes = Object.keys(latestByRoute);

  if (!events.length) return null;

  return (
    <section
      aria-label="Sovereign Action Stream"
      role="log"
      data-testid="sovereign-action-stream"
      style={{
        margin: '6px 12px 8px',
        padding: '10px 11px',
        borderRadius: 14,
        border: `1px solid ${C.border}`,
        background: 'rgba(15,23,42,0.72)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 8,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: stream.activeRoute ? C.sky : C.green,
            boxShadow: `0 0 6px ${stream.activeRoute ? C.sky : C.green}`,
          }}
        />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontFamily: 'monospace', fontSize: 10, color: C.textSub, fontWeight: 700 }}>
            Sovereign Action Stream
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 8.5, color: C.textMuted }}>
            {stream.activeRoute ? `aktive Route: ${stream.activeRoute}` : 'keine Route arbeitet unsichtbar'}
          </div>
        </div>
        {routes.length ? (
          <span style={{ fontFamily: 'monospace', fontSize: 8.5, color: C.textMuted }}>
            {routes.length} Routen
          </span>
        ) : null}
      </div>

      <div style={{ display: 'grid', gap: 6 }}>
        {events.map((event) => {
          const color = STATE_COLOR[event.state];
          return (
            <article
              key={eventKey(event)}
              data-route={event.route}
              data-state={event.state}
              style={{
                display: 'grid',
                gridTemplateColumns: '56px 1fr auto',
                alignItems: 'start',
                gap: 8,
                padding: '7px 8px',
                borderRadius: 10,
                border: `1px solid ${color}22`,
                background: `${color}0d`,
              }}
            >
              <span style={{ fontFamily: 'monospace', fontSize: 8.5, color: C.textMuted }}>
                {formatTime(event.createdAt)}
              </span>
              <span style={{ minWidth: 0 }}>
                <span style={{ display: 'block', fontFamily: 'monospace', fontSize: 10, color: C.text }}>
                  {event.label}
                </span>
                {event.detail ? (
                  <span style={{ display: 'block', marginTop: 2, fontSize: 11, color: C.textSub, lineHeight: 1.35 }}>
                    {event.detail}
                  </span>
                ) : (
                  <span className="sr-only">{describeSovereignActionEvent(event)}</span>
                )}
              </span>
              <span
                style={{
                  alignSelf: 'start',
                  border: `1px solid ${color}44`,
                  color,
                  borderRadius: 999,
                  padding: '2px 6px',
                  fontFamily: 'monospace',
                  fontSize: 8,
                  whiteSpace: 'nowrap',
                }}
              >
                {event.route} · {STATE_LABEL[event.state]}
              </span>
            </article>
          );
        })}
      </div>
    </section>
  );
}
