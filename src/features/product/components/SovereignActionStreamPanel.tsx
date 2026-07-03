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

function workerTitle(stream: SovereignActionStreamState): string {
  if (stream.activeRoute) return 'Sovereign arbeitet';
  if (stream.lastEvent?.state === 'blocked') return 'Sovereign wartet auf nächsten echten Schritt';
  if (stream.lastEvent?.state === 'failed') return 'Sovereign hat einen Blocker gefunden';
  return 'Sovereign hat den Arbeitsschritt protokolliert';
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
    <div
      aria-label="Sovereign Action Stream"
      role="log"
      data-testid="sovereign-action-stream"
      data-layout="chat-worker-bubble"
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: 8,
        padding: '2px 12px',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: 30,
          height: 30,
          borderRadius: 10,
          flexShrink: 0,
          background: C.surface,
          border: `1px solid ${C.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 13,
          color: C.textSub,
          marginBottom: 2,
        }}
      >
        ⬡
      </div>

      <section
        style={{
          maxWidth: '82%',
          padding: '11px 12px',
          borderRadius: '4px 18px 18px 18px',
          border: `1px solid ${C.border}`,
          background: C.asstBg,
          boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 7,
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
              flexShrink: 0,
            }}
          />
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontFamily: 'monospace', fontSize: 10, color: C.textSub, fontWeight: 700 }}>
              {workerTitle(stream)}
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

        <div style={{ display: 'grid', gap: 5 }}>
          {events.map((event) => {
            const color = STATE_COLOR[event.state];
            return (
              <article
                key={eventKey(event)}
                data-route={event.route}
                data-state={event.state}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '16px 1fr',
                  alignItems: 'start',
                  gap: 7,
                  padding: '6px 7px',
                  borderRadius: 10,
                  border: `1px solid ${color}22`,
                  background: `${color}0d`,
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: 8,
                    height: 8,
                    marginTop: 5,
                    borderRadius: '50%',
                    background: color,
                    boxShadow: event.state === 'running' ? `0 0 5px ${color}` : 'none',
                  }}
                />
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <span style={{ display: 'block', flex: 1, fontFamily: 'monospace', fontSize: 10, color: C.text }}>
                      {event.label}
                    </span>
                    <span
                      style={{
                        border: `1px solid ${color}44`,
                        color,
                        borderRadius: 999,
                        padding: '1px 5px',
                        fontFamily: 'monospace',
                        fontSize: 7.5,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {event.route} · {STATE_LABEL[event.state]}
                    </span>
                  </span>
                  {event.detail ? (
                    <span style={{ display: 'block', marginTop: 2, fontSize: 11, color: C.textSub, lineHeight: 1.35 }}>
                      {event.detail}
                    </span>
                  ) : (
                    <span className="sr-only">{describeSovereignActionEvent(event)}</span>
                  )}
                  <span style={{ display: 'block', marginTop: 2, fontFamily: 'monospace', fontSize: 8, color: C.textMuted }}>
                    {formatTime(event.createdAt)}
                  </span>
                </span>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
