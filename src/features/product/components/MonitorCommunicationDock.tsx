import React, { useMemo, useState } from 'react';
import { maskSecrets } from '../../../shared/utils/crypto';
import { C } from './builderConstants';
import type { SovereignLlmRouteOption } from '../runtime/devChatWorkerBridge';

export type SovereignChatKind = 'user' | 'assistant' | 'system';
export type SovereignChatToolchainState = 'checking' | 'ready' | 'blocked' | 'unavailable';

export interface SovereignChatEntry {
  readonly id: string;
  readonly kind: SovereignChatKind;
  readonly text: string;
  readonly createdAt: number;
}

export interface SovereignChatDockProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: () => void;
  readonly disabled: boolean;
  readonly busy: boolean;
  readonly entries: readonly SovereignChatEntry[];
  readonly routeOptions?: readonly SovereignLlmRouteOption[];
  readonly selectedRouteId?: string;
  readonly onRouteChange?: (routeId: string) => void;
  readonly routeCatalogError?: string | null;
  readonly routeHint?: string;
  readonly onOpenToolchain?: () => void;
  readonly toolchainState?: SovereignChatToolchainState;
  readonly toolsLauncher?: React.ReactNode;
  readonly onKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => boolean;
  readonly slashMenu?: React.ReactNode;
  readonly emptyState?: React.ReactNode;
}

const MAX_VISIBLE_ROUTE_RESULTS = 24;

function safeText(value: string, max = 900): string {
  const masked = maskSecrets(value.trim());
  if (!masked) return '';
  return masked.length > max ? `${masked.slice(0, max - 1)}…` : masked;
}

function routeSearchText(route: SovereignLlmRouteOption): string {
  return [route.id, route.label, route.provider, route.defaultModelId]
    .join(' ')
    .toLocaleLowerCase();
}

function routeBillingLabel(route: SovereignLlmRouteOption): string {
  return route.billingCategory === 'free' ? 'FREE' : 'PAID · Bestätigung vor Nutzung';
}

function railButtonStyle(active = false): React.CSSProperties {
  return {
    minWidth: 44,
    minHeight: 36,
    padding: '0 9px',
    borderRadius: 9,
    border: `1px solid ${active ? C.sky : C.border}`,
    background: active ? `${C.sky}18` : C.surface,
    color: active ? C.sky : C.textSub,
    cursor: 'pointer',
    font: '700 9px/1 monospace',
    letterSpacing: '.06em',
  };
}

export function SovereignChatDock({
  value,
  onChange,
  onSubmit,
  disabled,
  busy,
  entries,
  routeOptions = [],
  selectedRouteId = '',
  onRouteChange,
  routeCatalogError,
  routeHint,
  onOpenToolchain,
  toolchainState = 'unavailable',
  toolsLauncher,
  onKeyDown,
  slashMenu,
  emptyState,
}: SovereignChatDockProps) {
  const [routePickerOpen, setRoutePickerOpen] = useState(false);
  const [routeQuery, setRouteQuery] = useState('');
  const visibleEntries = entries.slice(-200);
  const visibleRouteHint = safeText(routeHint ?? '', 240);
  const selectedRoute = routeOptions.find((route) => route.id === selectedRouteId);
  const query = routeQuery.trim().toLocaleLowerCase();
  const matchingRoutes = useMemo(
    () => routeOptions.filter((route) => !query || routeSearchText(route).includes(query)),
    [query, routeOptions],
  );
  const visibleRoutes = matchingRoutes.slice(0, MAX_VISIBLE_ROUTE_RESULTS);
  const hiddenRouteCount = Math.max(0, matchingRoutes.length - visibleRoutes.length);
  const pickerLabel = selectedRoute
    ? `${routeBillingLabel(selectedRoute).split(' · ')[0]} · ${selectedRoute.provider} · ${selectedRoute.label}`
    : selectedRouteId
      ? `Fixierte Route nicht verfügbar · ${selectedRouteId}`
      : 'Auto · Backend/Revolver';
  const toolchainLabel = toolchainState === 'ready'
    ? 'bereit'
    : toolchainState === 'checking'
      ? 'prüft'
      : toolchainState === 'blocked'
        ? 'blockiert'
        : 'nicht verbunden';

  return (
    <section
      aria-label="Sovereign Chat"
      data-testid="sovereign-chat-dock"
      data-overlay="false"
      style={{
        flex: 1,
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        background: '#0b1016',
        color: C.text,
      }}
    >
      <ol
        aria-label="Chatverlauf"
        data-testid="sovereign-chat-body-window"
        style={{
          listStyle: 'none',
          margin: 0,
          padding: '18px clamp(12px, 4vw, 28px)',
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          minHeight: 0,
          gap: 12,
          overflowY: 'auto',
          overflowX: 'hidden',
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        {visibleEntries.length === 0 && emptyState ? (
          <li style={{ flex: 1, display: 'grid', placeItems: 'center', minHeight: '42vh' }}>
            {emptyState}
          </li>
        ) : null}
        {visibleEntries.map((entry) => {
          const text = safeText(entry.text);
          if (!text) return null;
          const accent = entry.kind === 'user' ? C.sky : C.green;
          return (
            <li
              key={entry.id}
              data-kind={entry.kind}
              style={{
                flex: '0 0 auto',
                alignSelf: entry.kind === 'user' ? 'flex-end' : 'flex-start',
                width: 'fit-content',
                minWidth: 0,
                maxWidth: 'min(760px, 88%)',
                padding: '10px 13px',
                borderRadius: 16,
                border: `1px solid ${accent}44`,
                background: entry.kind === 'user' ? `${C.sky}18` : `${C.green}0d`,
              }}
            >
              <strong style={{ display: 'block', color: accent, font: '700 9px/1.2 monospace', letterSpacing: '.08em' }}>
                {entry.kind === 'user' ? 'DU' : 'SOVEREIGN'}
              </strong>
              <span style={{ display: 'block', marginTop: 4, color: C.textSub, fontSize: 11, lineHeight: 1.45, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                {text}
              </span>
            </li>
          );
        })}
      </ol>

      <div
        data-testid="sovereign-chat-tool-row"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          padding: '7px 10px 0',
          background: '#0b1016',
        }}
      >
        <button
          type="button"
          onClick={onOpenToolchain}
          disabled={!onOpenToolchain}
          title={`Toolchain: ${toolchainLabel}`}
          style={railButtonStyle(toolchainState === 'ready')}
        >
          TOOLCHAIN
        </button>
        {toolsLauncher}
        <span
          role="status"
          style={{ marginLeft: 'auto', color: busy ? C.sky : C.textMuted, font: '9px/1.2 monospace' }}
        >
          {busy ? 'Agent Zero arbeitet…' : 'Bereit'}
        </span>
      </div>

      {onRouteChange && (
        <div
          data-testid="sovereign-llm-route-picker"
          style={{ position: 'relative', padding: '7px 10px 0' }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setRoutePickerOpen(false);
              setRouteQuery('');
            }
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <span style={{ color: C.textMuted, font: '9px/1 monospace' }}>LLM</span>
            <button
              type="button"
              data-testid="sovereign-llm-route-picker-trigger"
              aria-haspopup="dialog"
              aria-expanded={routePickerOpen}
              onClick={() => setRoutePickerOpen((open) => !open)}
              style={{
                flex: 1,
                minWidth: 0,
                minHeight: 38,
                padding: '7px 10px',
                borderRadius: 9,
                border: `1px solid ${routeCatalogError ? C.amber : selectedRouteId ? C.sky : C.border}`,
                background: '#080c11',
                color: selectedRouteId ? C.sky : C.text,
                textAlign: 'left',
                font: '10px/1.3 monospace',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {pickerLabel}
            </button>
            {selectedRouteId && (
              <button
                type="button"
                onClick={() => onRouteChange('')}
                aria-label="Chat LLM Route auf Auto zurücksetzen"
                style={railButtonStyle(false)}
              >
                AUTO
              </button>
            )}
          </div>

          {routePickerOpen && (
            <div
              role="dialog"
              aria-label="LLM-Modell auswählen"
              style={{
                marginTop: 6,
                padding: 8,
                borderRadius: 11,
                border: `1px solid ${C.border}`,
                background: C.surface,
                boxShadow: '0 12px 30px rgba(0,0,0,.35)',
              }}
            >
              <input
                autoFocus
                aria-label="Modelle durchsuchen"
                value={routeQuery}
                onChange={(event) => setRouteQuery(event.target.value)}
                placeholder="Provider, Modell oder Route suchen"
                style={{
                  boxSizing: 'border-box',
                  width: '100%',
                  minHeight: 40,
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: `1px solid ${C.border}`,
                  background: '#080c11',
                  color: C.text,
                }}
              />
              <div
                role="listbox"
                aria-label="Verfügbare LLM-Routen"
                style={{ marginTop: 6, maxHeight: 260, overflowY: 'auto', display: 'grid', gap: 4 }}
              >
                {visibleRoutes.map((route) => {
                  const paid = route.billingCategory !== 'free';
                  return (
                    <button
                      key={route.id}
                      type="button"
                      role="option"
                      aria-selected={route.id === selectedRouteId}
                      onClick={() => {
                        onRouteChange(route.id);
                        setRoutePickerOpen(false);
                        setRouteQuery('');
                      }}
                      style={{
                        minHeight: 44,
                        padding: '7px 9px',
                        borderRadius: 8,
                        border: `1px solid ${route.id === selectedRouteId ? C.sky : C.border}`,
                        background: route.id === selectedRouteId ? `${C.sky}12` : '#0b1016',
                        color: C.text,
                        textAlign: 'left',
                      }}
                    >
                      <span style={{ display: 'block', color: paid ? C.amber : C.green, font: '700 9px/1.2 monospace' }}>
                        {routeBillingLabel(route)}
                      </span>
                      <span style={{ display: 'block', marginTop: 3, fontSize: 11 }}>
                        {route.provider} · {route.label}
                      </span>
                      <span style={{ display: 'block', marginTop: 2, color: C.textMuted, font: '9px/1.2 monospace' }}>
                        {route.defaultModelId}
                      </span>
                    </button>
                  );
                })}
                {visibleRoutes.length === 0 && (
                  <p role="status" style={{ margin: 6, color: C.textMuted, fontSize: 10 }}>
                    Keine passende verifizierte Route.
                  </p>
                )}
              </div>
              {hiddenRouteCount > 0 && (
                <p style={{ margin: '7px 2px 0', color: C.textMuted, font: '9px/1.2 monospace' }}>
                  {hiddenRouteCount} weitere Treffer · Suche verfeinern
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {visibleRouteHint && !routeCatalogError && (
        <div data-testid="sovereign-route-hint" style={{ padding: '4px 10px 0', color: C.textMuted, font: '9px/1.3 monospace' }}>
          {visibleRouteHint}
        </div>
      )}
      {routeCatalogError && (
        <div role="status" style={{ padding: '4px 10px 0', color: C.amber, font: '9px/1.3 monospace' }}>
          Routenkatalog: {safeText(routeCatalogError, 240)}
        </div>
      )}
      {slashMenu ? <div style={{ padding: '6px 10px 0' }}>{slashMenu}</div> : null}

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
          aria-label="Codeauftrag an Sovereign"
          value={value}
          rows={1}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (onKeyDown?.(event)) return;
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              if (!disabled && !busy && value.trim()) onSubmit();
            }
          }}
          placeholder="Codeauftrag eingeben · Enter sendet · Shift+Enter neue Zeile"
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
          aria-label="Senden"
          title="Senden"
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
