import React from 'react';
import { maskSecrets } from '../../../shared/utils/crypto';
import { C } from './builderConstants';

export type MonitorCommunicationKind = 'user' | 'communicate' | 'runtime';

export interface MonitorCommunicationEntry {
  readonly id: string;
  readonly kind: MonitorCommunicationKind;
  readonly text: string;
  readonly createdAt: number;
}

export interface MonitorCommunicationDockProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: () => void;
  readonly disabled: boolean;
  readonly busy: boolean;
  readonly runtimeStatus: string;
  readonly entries: readonly MonitorCommunicationEntry[];
}

function safeText(value: string, max = 900): string {
  const masked = maskSecrets(value.trim());
  if (!masked) return '';
  return masked.length > max ? `${masked.slice(0, max - 1)}…` : masked;
}

function entryLabel(kind: MonitorCommunicationKind): string {
  if (kind === 'user') return 'YOU';
  if (kind === 'runtime') return 'RUNTIME';
  return 'COMMUNICATE';
}

export function MonitorCommunicationDock({
  value,
  onChange,
  onSubmit,
  disabled,
  busy,
  runtimeStatus,
  entries,
}: MonitorCommunicationDockProps) {
  const visibleEntries = entries.slice(-3);
  const status = safeText(runtimeStatus, 240) || 'Runtimestatus nicht verfügbar';

  return (
    <section
      aria-label="Monitor Kommunikation"
      data-testid="monitor-communication-dock"
      data-overlay="false"
      style={{
        flexShrink: 0,
        borderTop: `1px solid ${C.border}`,
        background: '#0b1016',
        color: C.text,
      }}
    >
      <div
        role="status"
        aria-live="polite"
        title="Beobachtbarer Runtime-Status; keine verborgene Modell-Gedankenkette."
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          minHeight: 32,
          padding: '5px 10px',
          borderBottom: visibleEntries.length ? `1px solid ${C.border}` : undefined,
          color: C.textSub,
          font: '10px/1.35 monospace',
        }}
      >
        <strong style={{ color: C.violet, letterSpacing: '.08em' }}>THINK</strong>
        <span aria-hidden="true" style={{ color: C.textMuted }}>·</span>
        <span data-testid="monitor-runtime-status" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {status}
        </span>
      </div>

      {visibleEntries.length > 0 && (
        <ol
          aria-label="Letzte Monitor-Kommunikation"
          data-testid="monitor-communication-bubbles"
          style={{
            listStyle: 'none',
            margin: 0,
            padding: '7px 10px',
            display: 'flex',
            gap: 7,
            overflowX: 'auto',
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          {visibleEntries.map((entry) => {
            const text = safeText(entry.text);
            if (!text) return null;
            const accent = entry.kind === 'user' ? C.sky : entry.kind === 'runtime' ? C.amber : C.green;
            return (
              <li
                key={entry.id}
                data-kind={entry.kind}
                style={{
                  flex: '0 1 min(420px, 78vw)',
                  minWidth: 'min(230px, 68vw)',
                  maxHeight: 86,
                  overflowY: 'auto',
                  padding: '7px 9px',
                  borderRadius: 10,
                  border: `1px solid ${accent}44`,
                  background: `${accent}0d`,
                }}
              >
                <strong style={{ display: 'block', color: accent, font: '700 9px/1.2 monospace', letterSpacing: '.08em' }}>
                  {entryLabel(entry.kind)}
                </strong>
                <span style={{ display: 'block', marginTop: 4, color: C.textSub, fontSize: 11, lineHeight: 1.45, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                  {text}
                </span>
              </li>
            );
          })}
        </ol>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!disabled && !busy && value.trim()) onSubmit();
        }}
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 7,
          padding: '8px 10px max(8px, env(safe-area-inset-bottom))',
        }}
      >
        <textarea
          aria-label="Frage an Sovereign während Live Monitor"
          value={value}
          rows={1}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              if (!disabled && !busy && value.trim()) onSubmit();
            }
          }}
          placeholder="Frage stellen, ohne den Monitor zu verlassen…"
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 44,
            maxHeight: 88,
            resize: 'vertical',
            padding: '10px 12px',
            borderRadius: 11,
            border: `1px solid ${C.border}`,
            background: '#080c11',
            color: C.text,
            outline: 'none',
            font: '12px/1.45 system-ui, sans-serif',
          }}
        />
        <button
          type="submit"
          aria-label="Monitor Frage senden"
          disabled={disabled || busy || !value.trim()}
          style={{
            width: 44,
            height: 44,
            flexShrink: 0,
            border: 0,
            borderRadius: 11,
            background: disabled || busy || !value.trim() ? C.surface : C.sky,
            color: disabled || busy || !value.trim() ? C.textMuted : '#041017',
            cursor: disabled || busy || !value.trim() ? 'not-allowed' : 'pointer',
            fontSize: 16,
            fontWeight: 800,
          }}
        >
          {busy ? '…' : '↑'}
        </button>
      </form>
    </section>
  );
}
