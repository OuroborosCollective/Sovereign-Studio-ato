import React, { useMemo, useState } from 'react';
import { maskSecrets } from '../../../shared/utils/crypto';
import { C } from './builderConstants';
import type { SovereignLlmRouteOption } from '../runtime/devChatWorkerBridge';

export type MonitorCommunicationKind = 'user' | 'communicate' | 'runtime';
export type MonitorToolchainState = 'checking' | 'ready' | 'blocked' | 'unavailable';

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
  readonly routeOptions?: readonly SovereignLlmRouteOption[];
  readonly selectedRouteId?: string;
  readonly onRouteChange?: (routeId: string) => void;
  readonly routeCatalogError?: string | null;
  readonly routeHint?: string;
  readonly runtimeMood?: string;
  readonly onOpenFlow?: () => void;
  readonly onRequestIdea?: () => void;
  readonly onOpenToolchain?: () => void;
  readonly toolchainState?: MonitorToolchainState;
  readonly toolsLauncher?: React.ReactNode;
  readonly onKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => boolean;
  readonly slashMenu?: React.ReactNode;
  readonly mode?: 'monitor' | 'chat';
  readonly emptyState?: React.ReactNode;
}

const MAX_VISIBLE_ROUTE_RESULTS = 24;

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

export function MonitorCommunicationDock({
  value,
  onChange,
  onSubmit,
  disabled,
  busy,
  runtimeStatus,
  entries,
  routeOptions = [],
  selectedRouteId = '',
  onRouteChange,
  routeCatalogError,
  routeHint,
  runtimeMood = '😊✨',
  onOpenFlow,
  onRequestIdea,
  onOpenToolchain,
  toolchainState = 'unavailable',
  toolsLauncher,
  onKeyDown,
  slashMenu,
  mode = 'monitor',
  emptyState,
}: MonitorCommunicationDockProps) {
  const [routePickerOpen, setRoutePickerOpen] = useState(false);
  const [routeQuery, setRouteQuery] = useState('');
  const chatMode = mode === 'chat';
  const visibleEntryIds = new Set(entries.slice(-4).map((entry) => entry.id));
  entries
    .filter((entry) => entry.kind === 'user')
    .slice(-2)
    .forEach((entry) => visibleEntryIds.add(entry.id));
  const visibleEntries = chatMode
    ? entries
    : entries.filter((entry) => visibleEntryIds.has(entry.id)).slice(-6);
  const status = safeText(runtimeStatus, 240) || 'Runtimestatus nicht verfügbar';
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
      aria-label={chatMode ? 'Sovereign Chat' : 'Monitor Kommunikation'}
      data-testid="monitor-communication-dock"
      data-mode={mode}
      data-overlay="false"
      style={{
        flexShrink: chatMode ? 1 : 0,
        flex: chatMode ? 1 : undefined,
        minHeight: chatMode ? 0 : undefined,
        display: chatMode ? 'flex' : undefined,
        flexDirection: chatMode ? 'column' : undefined,
        borderTop: chatMode ? 0 : `1px solid ${C.border}`,
        background: '#0b1016',
        color: C.text,
      }}
    >
      <div
        data-testid="monitor-status-rail"
        style={{
          display: chatMode ? 'none' : 'flex',
          alignItems: 'center',
          gap: 6,
          minHeight: 46,
          padding: '5px 10px',
          borderBottom: `1px solid ${C.border}`,
          flexWrap: 'wrap',
        }}
      >
        <span
          title="Beobachtbarer Runtime-Status; keine verborgene Modell-Gedankenkette."
          style={{ ...railButtonStyle(busy), display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
        >
          THINK
        </span>
        <button type="button" onClick={onOpenFlow} disabled={!onOpenFlow} style={railButtonStyle(false)}>
          FLOW
        </button>
        <button
          type="button"
          onClick={onRequestIdea}
          disabled={!onRequestIdea || busy}
          style={{ ...railButtonStyle(false), opacity: !onRequestIdea || busy ? 0.5 : 1 }}
        >
          IDEA
        </button>
        <span
          aria-label={busy ? 'Sovereign arbeitet' : 'Sovereign bereit'}
          title={busy ? 'Runtime arbeitet' : 'Runtime wartet auf Auftrag'}
          style={{ minWidth: 44, textAlign: 'center', fontSize: 17 }}
        >
          {runtimeMood}
        </span>
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
      </div>

      <div
        role="status"
        aria-live="polite"
        data-testid="monitor-runtime-status"
        style={{
          display: chatMode ? 'none' : undefined,
          minHeight: 27,
          padding: '5px 10px',
          color: C.textSub,
          font: '10px/1.35 monospace',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {status}
      </div>

      {(chatMode || visibleEntries.length > 0) && (
        <ol
          aria-label={chatMode ? 'Chatverlauf' : 'Letzte Monitor-Kommunikation'}
          data-testid={chatMode ? 'sovereign-chat-body-window' : 'monitor-communication-bubbles'}
          style={{
            listStyle: 'none',
            margin: 0,
            padding: chatMode ? '18px clamp(12px, 4vw, 28px)' : '7px 10px',
            display: 'flex',
            flexDirection: chatMode ? 'column' : undefined,
            flex: chatMode ? 1 : undefined,
            minHeight: chatMode ? 0 : undefined,
            gap: chatMode ? 12 : 7,
            overflowY: chatMode ? 'auto' : undefined,
            overflowX: chatMode ? 'hidden' : 'auto',
            borderTop: chatMode ? 0 : `1px solid ${C.border}`,
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          {chatMode && visibleEntries.length === 0 && emptyState ? (
            <li style={{ flex: 1, display: 'grid', placeItems: 'center', minHeight: '42vh' }}>
              {emptyState}
            </li>
          ) : null}
          {visibleEntries.map((entry) => {
            const text = safeText(entry.text);
            if (!text) return null;
            const accent = entry.kind === 'user' ? C.sky : entry.kind === 'runtime' ? C.amber : C.green;
            return (
              <li
                key={entry.id}
                data-kind={entry.kind}
                style={{
                  flex: chatMode ? '0 0 auto' : '0 1 min(420px, 78vw)',
                  alignSelf: chatMode ? (entry.kind === 'user' ? 'flex-end' : 'flex-start') : undefined,
                  width: chatMode ? 'fit-content' : undefined,
                  minWidth: chatMode ? 0 : 'min(230px, 68vw)',
                  maxWidth: chatMode ? 'min(760px, 88%)' : undefined,
                  maxHeight: chatMode ? 'none' : 86,
                  overflowY: chatMode ? 'visible' : 'auto',
                  padding: chatMode ? '10px 13px' : '7px 9px',
                  borderRadius: chatMode ? 16 : 10,
                  border: `1px solid ${accent}44`,
                  background: entry.kind === 'user' && chatMode ? `${C.sky}18` : `${accent}0d`,
                }}
              >
                <strong style={{ display: 'block', color: accent, font: '700 9px/1.2 monospace', letterSpacing: '.08em' }}>
                  {chatMode
                    ? entry.kind === 'user' ? 'DU' : entry.kind === 'runtime' ? 'STATUS' : 'SOVEREIGN'
                    : entryLabel(entry.kind)}
                </strong>
                <span style={{ display: 'block', marginTop: 4, color: C.textSub, fontSize: 11, lineHeight: 1.45, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                  {text}
                </span>
              </li>
            );
          })}
        </ol>
      )}

      {chatMode && (
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
            {busy ? 'Agent arbeitet…' : 'Bereit'}
          </span>
        </div>
      )}

      {onRouteChange && (
        <div
          data-testid="monitor-llm-route-picker"
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
                aria-label={chatMode ? 'Chat LLM Route auf Auto zurücksetzen' : 'Monitor LLM Route auf Auto zurücksetzen'}
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
        <div data-testid="monitor-route-hint" style={{ padding: '4px 10px 0', color: C.textMuted, font: '9px/1.3 monospace' }}>
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
