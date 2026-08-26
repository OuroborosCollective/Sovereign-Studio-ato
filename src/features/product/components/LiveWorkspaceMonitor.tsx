import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { VncScreen } from 'react-vnc';
import { maskSecrets } from '../../../shared/utils/crypto';
import type {
  SovereignAgentJobSnapshot,
  SovereignLiveProjection,
  SovereignLiveProjectionKind,
  SovereignLiveProjectionState,
} from '../runtime/sovereignAgentRuntime';
import { C } from './builderConstants';

export interface LiveWorkspaceMonitorProps {
  readonly projections: readonly SovereignLiveProjection[];
  readonly job?: SovereignAgentJobSnapshot | null;
  readonly desktopStream?: {
    readonly url: string;
    readonly activationId: string;
    readonly sessionBindingHash: string;
    readonly expiresAtEpoch: number;
  } | null;
}

interface MonitorTab {
  readonly kind: SovereignLiveProjectionKind;
  readonly label: string;
  readonly icon: string;
}

const MONITOR_TABS: readonly MonitorTab[] = [
  { kind: 'IDE_FILE', label: 'Editor', icon: '⌘' },
  { kind: 'IDE_DIFF', label: 'Diff', icon: '±' },
  { kind: 'TERMINAL', label: 'Terminal', icon: '>_' },
  { kind: 'BROWSER', label: 'Browser', icon: '◎' },
  { kind: 'WINDOW_FOCUS', label: 'Focus', icon: '▣' },
];

const PROJECTION_STATE_VIEW: Readonly<Record<SovereignLiveProjectionState, {
  readonly label: string;
  readonly description: string;
  readonly color: string;
  readonly icon: string;
}>> = {
  REQUESTED: {
    label: 'Angefordert',
    description: 'Die kanonische Aktion hat eine Darstellung angefordert.',
    color: C.sky,
    icon: '→',
  },
  VISIBLE: {
    label: 'Sichtbar',
    description: 'Die Darstellung wurde als Monitorbeobachtung zurückgemeldet.',
    color: C.green,
    icon: '◉',
  },
  UNAVAILABLE: {
    label: 'Nicht verfügbar',
    description: 'Für diese Aktion liegt keine darstellbare Monitorbeobachtung vor.',
    color: C.rose,
    icon: '⊘',
  },
  STALE: {
    label: 'Veraltet',
    description: 'Die Darstellung gehört nicht mehr zu einem frischen Workspace-Readback.',
    color: C.amber,
    icon: '↺',
  },
};

function shortIdentity(value: string | null | undefined, width = 12): string {
  if (!value) return '—';
  return value.length > width ? `${value.slice(0, width)}…` : value;
}

function boundedText(value: unknown, maximum = 12_000): string {
  if (typeof value !== 'string') return '';
  const safe = maskSecrets(value);
  return safe.length > maximum ? `${safe.slice(0, maximum - 1)}…` : safe;
}

function payloadText(
  payload: Readonly<Record<string, unknown>>,
  keys: readonly string[],
  maximum = 2000,
): string {
  for (const key of keys) {
    const value = boundedText(payload[key], maximum).trim();
    if (value) return value;
  }
  return '';
}

function payloadNumber(
  payload: Readonly<Record<string, unknown>>,
  keys: readonly string[],
): number | null {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

function payloadBoolean(
  payload: Readonly<Record<string, unknown>>,
  keys: readonly string[],
): boolean | null {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === 'boolean') return value;
  }
  return null;
}

function payloadStringArray(
  payload: Readonly<Record<string, unknown>>,
  keys: readonly string[],
  maximum = 24,
): string[] {
  for (const key of keys) {
    const value = payload[key];
    if (!Array.isArray(value)) continue;
    return value
      .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      .slice(0, maximum)
      .map((item) => boundedText(item, 240));
  }
  return [];
}

function currentBinding(projections: readonly SovereignLiveProjection[]): SovereignLiveProjection[] {
  const latest = projections.at(-1);
  if (!latest) return [];
  return projections.filter((projection) => (
    projection.sessionBindingHash === latest.sessionBindingHash
    && projection.attemptId === latest.attemptId
    && projection.workspaceId === latest.workspaceId
  ));
}

function latestByKind(
  projections: readonly SovereignLiveProjection[],
): ReadonlyMap<SovereignLiveProjectionKind, SovereignLiveProjection> {
  const byKind = new Map<SovereignLiveProjectionKind, SovereignLiveProjection>();
  for (const projection of projections) byKind.set(projection.projectionKind, projection);
  return byKind;
}

function MetaPill({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        minHeight: 26,
        padding: '3px 7px',
        borderRadius: 7,
        border: `1px solid ${C.border}`,
        background: '#0b0f14',
        color: C.textSub,
        fontFamily: 'monospace',
        fontSize: 10,
        overflowWrap: 'anywhere',
      }}
    >
      <span style={{ color: C.textMuted }}>{label}</span>
      <strong style={{ color: C.text, fontWeight: 600 }}>{value}</strong>
    </span>
  );
}

function DesktopFramePane({ stream, job }: { readonly stream?: LiveWorkspaceMonitorProps['desktopStream']; readonly job?: SovereignAgentJobSnapshot | null; }) {
  return (
    <div className="live-workspace-monitor__desktop" data-testid="live-workspace-monitor-desktop">
      <div className="live-workspace-monitor__surface-toolbar"><span style={{ color: C.green }}>DESKTOP · LIVE RFB STREAM</span><span>{stream ? 'CONNECTED · VIEW ONLY' : 'warte auf Desktop-Worker'}</span></div>
      {stream ? (<>
        <div className="live-workspace-monitor__desktop-frame-wrap" data-testid="live-workspace-monitor-rfb-stream"><VncScreen key={`${stream.activationId}:${stream.expiresAtEpoch}`} url={stream.url} scaleViewport viewOnly rfbOptions={{ secure: false, shared: true, wsProtocols: ['binary'] }} style={{ width: '100%', height: '100%', minHeight: 420 }} /></div>
        <div className="live-workspace-monitor__metadata-grid"><MetaPill label="Activation" value={shortIdentity(stream.activationId, 20)} /><MetaPill label="Session" value={shortIdentity(stream.sessionBindingHash, 20)} /><MetaPill label="Job" value={shortIdentity(job?.jobId, 18)} /></div>
      </>) : (<div className="live-workspace-monitor__honest-empty" data-testid="live-workspace-monitor-desktop-unavailable"><span aria-hidden="true">▣</span><p>{job?.jobId ? 'Der Monitor wartet auf den echten Desktop-Worker und seinen RFB-WebSocket. Es werden keine Ersatzbilder erzeugt.' : 'Noch kein aktiver Workspace-Job. Der Live-Desktop startet mit dem ersten echten AttemptWorkspace.'}</p></div>)}
    </div>
  );
}

function EmptyProjectionPane() {
  return (
    <div
      data-testid="live-workspace-monitor-empty"
      style={{
        minHeight: 250,
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        textAlign: 'center',
        background: 'radial-gradient(circle at 50% 35%, rgba(34,211,238,.08), transparent 45%)',
      }}
    >
      <div style={{ maxWidth: 420 }}>
        <div aria-hidden="true" style={{ fontSize: 32, color: C.textMuted, marginBottom: 10 }}>▱</div>
        <strong style={{ display: 'block', color: C.text, fontSize: 13 }}>
          Keine gebundene Monitor-Beobachtung
        </strong>
        <p style={{ margin: '7px 0 0', color: C.textSub, fontSize: 11.5, lineHeight: 1.55 }}>
          Der Monitor bleibt leer, bis die Runtime ein kanonisches Projection-Event für den aktuellen
          Attempt liefert. Es wird keine Aktivität simuliert.
        </p>
      </div>
    </div>
  );
}

function FilePane({ projection }: { readonly projection: SovereignLiveProjection }) {
  const path = payloadText(projection.payload, ['path', 'filePath', 'relativePath'], 500);
  const mode = payloadText(projection.payload, ['mode', 'operation'], 80);
  const contentHash = payloadText(projection.payload, ['contentSha256', 'contentHash'], 100);
  return (
    <div className="live-workspace-monitor__surface live-workspace-monitor__editor" data-testid="live-workspace-monitor-editor">
      <div className="live-workspace-monitor__surface-toolbar">
        <span style={{ color: C.sky }}>EDITOR</span>
        <span title={path || undefined} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {path || 'Keine freigegebene Dateireferenz'}
        </span>
      </div>
      <div className="live-workspace-monitor__metadata-grid">
        <MetaPill label="Pfad" value={path || 'nicht geliefert'} />
        <MetaPill label="Modus" value={mode || 'nicht geliefert'} />
        <MetaPill label="Inhalt" value={shortIdentity(contentHash, 18)} />
        <MetaPill label="Head" value={shortIdentity(projection.repositoryHead, 14)} />
      </div>
      <div className="live-workspace-monitor__honest-empty">
        <span aria-hidden="true">{path ? '⌘' : '—'}</span>
        <p>
          {path
            ? 'Die Runtime hat die gebundene Datei referenziert. Dateiinhalte werden hier nicht erfunden oder aus ungeprüften Payload-Feldern übernommen.'
            : 'Das Projection-Event enthält keinen freigegebenen Dateipfad.'}
        </p>
      </div>
    </div>
  );
}

function DiffPane({ projection }: { readonly projection: SovereignLiveProjection }) {
  const changedFiles = payloadStringArray(projection.payload, ['changedFiles', 'files']);
  const diffHash = payloadText(projection.payload, ['diffSha256', 'diffHash'], 100);
  return (
    <div className="live-workspace-monitor__surface live-workspace-monitor__diff" data-testid="live-workspace-monitor-diff">
      <div className="live-workspace-monitor__surface-toolbar">
        <span style={{ color: C.violet }}>DIFF</span>
        <span>{changedFiles.length} gebundene Datei{changedFiles.length === 1 ? '' : 'en'}</span>
      </div>
      <div className="live-workspace-monitor__metadata-grid">
        <MetaPill label="Diff" value={shortIdentity(diffHash, 18)} />
        <MetaPill label="Head" value={shortIdentity(projection.repositoryHead, 14)} />
        <MetaPill label="Action" value={shortIdentity(projection.actionId, 14)} />
      </div>
      {changedFiles.length > 0 ? (
        <ol className="live-workspace-monitor__file-list" aria-label="Gebundene Diff-Dateien">
          {changedFiles.map((path, index) => (
            <li key={`${path}-${index}`}>
              <span aria-hidden="true" style={{ color: C.textMuted }}>±</span>
              <code>{path}</code>
            </li>
          ))}
        </ol>
      ) : (
        <div className="live-workspace-monitor__honest-empty">
          <span aria-hidden="true">—</span>
          <p>Das Projection-Event enthält keine freigegebene Changed-File-Liste; es werden keine Diffzeilen simuliert.</p>
        </div>
      )}
    </div>
  );
}

function TerminalPane({ projection }: { readonly projection: SovereignLiveProjection }) {
  const chunk = payloadText(projection.payload, ['chunk', 'output', 'text'], 16_000);
  const channel = payloadText(projection.payload, ['channel', 'stream'], 80);
  const processState = payloadText(projection.payload, ['processState', 'state'], 80);
  const canonicalStatus = payloadText(projection.payload, ['canonicalStatus'], 80);
  const exitCode = payloadNumber(projection.payload, ['exitCode']);
  const successful = payloadBoolean(projection.payload, ['successful']);
  return (
    <div className="live-workspace-monitor__surface live-workspace-monitor__terminal" data-testid="live-workspace-monitor-terminal">
      <div className="live-workspace-monitor__surface-toolbar">
        <span style={{ color: C.green }}>&gt;_ TERMINAL</span>
        <span>{channel || 'Kanal nicht geliefert'}</span>
      </div>
      <div className="live-workspace-monitor__metadata-grid">
        <MetaPill label="Prozess" value={processState || 'nicht geliefert'} />
        <MetaPill label="Exit" value={exitCode === null ? '—' : String(exitCode)} />
        <MetaPill label="Status" value={canonicalStatus || 'nicht geliefert'} />
        <MetaPill label="Signal" value={successful === null ? '—' : successful ? 'positiv beobachtet' : 'nicht positiv'} />
      </div>
      <pre className="live-workspace-monitor__terminal-output">
        {chunk || 'Keine freigegebene Prozessausgabe im Projection-Event.'}
      </pre>
      <p className="live-workspace-monitor__pane-notice">
        Exitcode und Prozessausgabe sind Beobachtungen. Sie verifizieren weder Deployment noch Zielwirkung.
      </p>
    </div>
  );
}

function BrowserPane({ projection }: { readonly projection: SovereignLiveProjection }) {
  const title = payloadText(projection.payload, ['title', 'pageTitle', 'windowTitle'], 300);
  const url = payloadText(projection.payload, ['url', 'targetUrl', 'href'], 1000);
  const frameHash = payloadText(projection.payload, ['frameHash', 'screenshotSha256'], 100);
  return (
    <div className="live-workspace-monitor__surface live-workspace-monitor__browser" data-testid="live-workspace-monitor-browser">
      <div className="live-workspace-monitor__browser-bar">
        <span aria-hidden="true" className="live-workspace-monitor__browser-controls">● ● ●</span>
        <div title={url || undefined} className="live-workspace-monitor__address">
          {url || 'Keine freigegebene Browser-URL im Projection-Event'}
        </div>
      </div>
      <div className="live-workspace-monitor__metadata-grid">
        <MetaPill label="Titel" value={title || 'nicht geliefert'} />
        <MetaPill label="Frame" value={shortIdentity(frameHash, 18)} />
        <MetaPill label="Head" value={shortIdentity(projection.repositoryHead, 14)} />
      </div>
      <div className="live-workspace-monitor__honest-empty">
        <span aria-hidden="true">◎</span>
        <p>
          {url
            ? 'Die Browserreferenz ist gebunden. Ohne echten Frame-Readback wird keine Webseite nachgezeichnet.'
            : 'Für diese Beobachtung liegt keine freigegebene Browseransicht vor.'}
        </p>
      </div>
    </div>
  );
}

function FocusPane({ projection }: { readonly projection: SovereignLiveProjection }) {
  const application = payloadText(projection.payload, ['application', 'app', 'process'], 240);
  const title = payloadText(projection.payload, ['title', 'windowTitle'], 500);
  const windowId = payloadText(projection.payload, ['windowId', 'targetId'], 200);
  return (
    <div className="live-workspace-monitor__surface live-workspace-monitor__focus" data-testid="live-workspace-monitor-focus">
      <div className="live-workspace-monitor__surface-toolbar">
        <span style={{ color: C.amber }}>WINDOW FOCUS</span>
        <span>{application || 'Anwendung nicht geliefert'}</span>
      </div>
      <div className="live-workspace-monitor__metadata-grid">
        <MetaPill label="Fenster" value={title || 'nicht geliefert'} />
        <MetaPill label="ID" value={shortIdentity(windowId, 18)} />
        <MetaPill label="Action" value={shortIdentity(projection.actionId, 14)} />
      </div>
      <div className="live-workspace-monitor__honest-empty">
        <span aria-hidden="true">▣</span>
        <p>Der Fokus ist eine korrelierte GUI-Beobachtung und erteilt keine Eingabe-, Consent- oder Effekt-Autorität.</p>
      </div>
    </div>
  );
}

function ProjectionPane({ projection }: { readonly projection: SovereignLiveProjection | null }) {
  if (!projection) return <EmptyProjectionPane />;
  if (projection.projectionKind === 'IDE_FILE') return <FilePane projection={projection} />;
  if (projection.projectionKind === 'IDE_DIFF') return <DiffPane projection={projection} />;
  if (projection.projectionKind === 'TERMINAL') return <TerminalPane projection={projection} />;
  if (projection.projectionKind === 'BROWSER') return <BrowserPane projection={projection} />;
  return <FocusPane projection={projection} />;
}

function ObservationRail({
  projections,
  selectedKind,
  onSelect,
}: {
  readonly projections: readonly SovereignLiveProjection[];
  readonly selectedKind: SovereignLiveProjectionKind | null;
  readonly onSelect: (kind: SovereignLiveProjectionKind) => void;
}) {
  const visible = projections.slice(-8).reverse();
  return (
    <aside className="live-workspace-monitor__rail" aria-label="Gebundene Monitorbeobachtungen">
      <div className="live-workspace-monitor__rail-heading">
        <span>OBSERVATIONS</span>
        <strong>{projections.length}</strong>
      </div>
      {visible.length === 0 ? (
        <p className="live-workspace-monitor__rail-empty">Noch kein Projection-Event für den aktuellen Attempt.</p>
      ) : (
        <ol>
          {visible.map((projection, index) => {
            const state = PROJECTION_STATE_VIEW[projection.projectionState];
            const selected = selectedKind === projection.projectionKind;
            return (
              <li key={`${projection.projectionId}-${index}`}>
                <button
                  type="button"
                  onClick={() => onSelect(projection.projectionKind)}
                  aria-label={`${projection.projectionKind}: ${state.label}`}
                  aria-pressed={selected}
                  style={{ borderColor: selected ? state.color : C.border }}
                >
                  <span aria-hidden="true" style={{ color: state.color }}>{state.icon}</span>
                  <span className="live-workspace-monitor__rail-copy">
                    <strong>{MONITOR_TABS.find((tab) => tab.kind === projection.projectionKind)?.label ?? projection.projectionKind}</strong>
                    <small>{state.label} · {shortIdentity(projection.actionId, 12)}</small>
                  </span>
                  <code>{shortIdentity(projection.sourceReceiptRef, 8)}</code>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </aside>
  );
}

export function LiveWorkspaceMonitor({ projections, job, desktopStream }: LiveWorkspaceMonitorProps) {
  const monitorId = useId().replace(/:/g, '');
  const current = useMemo(() => currentBinding(projections), [projections]);
  const projectionMap = useMemo(() => latestByKind(current), [current]);
  const latest = current.at(-1) ?? null;
  const defaultKind = latest?.projectionKind ?? null;
  const bindingKey = latest
    ? `${latest.sessionBindingHash}:${latest.attemptId}:${latest.workspaceId}`
    : 'no-current-binding';
  const [selectedKind, setSelectedKind] = useState<SovereignLiveProjectionKind | null>(defaultKind);
  const previousBindingKey = useRef(bindingKey);

  useEffect(() => {
    const bindingChanged = previousBindingKey.current !== bindingKey;
    previousBindingKey.current = bindingKey;
    if (bindingChanged || !selectedKind || !projectionMap.has(selectedKind)) {
      setSelectedKind(defaultKind);
    }
  }, [bindingKey, defaultKind, projectionMap, selectedKind]);

  const selectedProjection = selectedKind ? projectionMap.get(selectedKind) ?? null : null;
  const selectedState = selectedProjection
    ? PROJECTION_STATE_VIEW[selectedProjection.projectionState]
    : null;

  return (
    <section
      role="region"
      aria-label="Sovereign Live Workspace Monitor"
      data-testid="live-workspace-monitor"
      data-binding-key={bindingKey}
      style={{
        borderTop: `1px solid ${C.border}`,
        background: '#090d12',
        color: C.text,
      }}
    >
      <style>{`
        .live-workspace-monitor__chrome {
          display: flex;
          align-items: center;
          gap: 10px;
          min-height: 54px;
          padding: 8px 12px;
          border-bottom: 1px solid ${C.border};
          background: linear-gradient(180deg, #141b24 0%, #0d1218 100%);
        }
        .live-workspace-monitor__title { min-width: 0; flex: 1; }
        .live-workspace-monitor__title strong { display: block; font: 700 11px/1.2 monospace; letter-spacing: .12em; color: ${C.text}; }
        .live-workspace-monitor__title small { display: block; margin-top: 3px; color: ${C.textMuted}; font: 9.5px/1.25 monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .live-workspace-monitor__authority-badge {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          min-height: 28px;
          padding: 3px 8px;
          border: 1px solid ${C.amber}55;
          border-radius: 999px;
          color: ${C.amber};
          background: ${C.amber}0d;
          font: 700 9px/1 monospace;
          letter-spacing: .05em;
          white-space: nowrap;
        }
        .live-workspace-monitor__tabs {
          display: flex;
          gap: 2px;
          min-width: 0;
          overflow-x: auto;
          padding: 4px 6px;
          border-bottom: 1px solid ${C.border};
          background: #0d1218;
          scrollbar-width: thin;
        }
        .live-workspace-monitor__tab {
          min-width: 92px;
          min-height: 44px;
          padding: 6px 10px;
          border: 1px solid transparent;
          border-radius: 8px;
          background: transparent;
          color: ${C.textMuted};
          font: 600 10.5px/1 monospace;
          cursor: pointer;
          white-space: nowrap;
        }
        .live-workspace-monitor__tab[aria-selected="true"] { border-color: ${C.sky}55; background: ${C.sky}10; color: ${C.sky}; }
        .live-workspace-monitor__tab:disabled { cursor: not-allowed; opacity: .34; }
        .live-workspace-monitor__layout { display: grid; grid-template-columns: minmax(0, 1fr) 270px; min-height: 310px; }
        .live-workspace-monitor__main { min-width: 0; border-right: 1px solid ${C.border}; }
        .live-workspace-monitor__pane-header {
          display: flex;
          align-items: center;
          gap: 8px;
          min-height: 40px;
          padding: 6px 10px;
          border-bottom: 1px solid ${C.border};
          color: ${C.textSub};
          font: 10px/1.3 monospace;
        }
        .live-workspace-monitor__pane-header strong { color: ${C.text}; }
        .live-workspace-monitor__state { margin-left: auto; display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
        .live-workspace-monitor__surface { min-height: 270px; background: #090d12; }
        .live-workspace-monitor__desktop { background: #05080c; border-bottom: 1px solid ${C.border}; }
        .live-workspace-monitor__desktop-frame-wrap { min-height: 220px; max-height: 52vh; display: grid; place-items: center; overflow: auto; background: #020406; }
        .live-workspace-monitor__desktop-frame { display: block; max-width: 100%; max-height: 52vh; width: auto; height: auto; object-fit: contain; image-rendering: auto; }
        .live-workspace-monitor__surface-toolbar,
        .live-workspace-monitor__browser-bar {
          min-height: 38px;
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 6px 10px;
          border-bottom: 1px solid ${C.border};
          color: ${C.textSub};
          font: 10px/1.2 monospace;
        }
        .live-workspace-monitor__surface-toolbar span:first-child { flex-shrink: 0; font-weight: 700; letter-spacing: .08em; }
        .live-workspace-monitor__metadata-grid { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px; border-bottom: 1px solid ${C.border}; }
        .live-workspace-monitor__honest-empty { min-height: 150px; display: grid; place-items: center; align-content: center; gap: 8px; padding: 20px; color: ${C.textMuted}; text-align: center; }
        .live-workspace-monitor__honest-empty > span { font-size: 24px; }
        .live-workspace-monitor__honest-empty p { max-width: 520px; margin: 0; color: ${C.textSub}; font-size: 11.5px; line-height: 1.55; }
        .live-workspace-monitor__terminal-output { min-height: 130px; max-height: 240px; margin: 0; padding: 12px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; color: ${C.text}; background: #05080c; font: 11px/1.55 monospace; }
        .live-workspace-monitor__pane-notice { margin: 0; padding: 8px 10px; border-top: 1px solid ${C.border}; color: ${C.amber}; font-size: 10.5px; line-height: 1.45; }
        .live-workspace-monitor__file-list { list-style: none; margin: 0; padding: 8px 10px 12px; display: grid; gap: 5px; }
        .live-workspace-monitor__file-list li { display: flex; align-items: center; gap: 8px; min-height: 30px; padding: 4px 7px; border: 1px solid ${C.border}; border-radius: 6px; color: ${C.textSub}; background: #0b0f14; }
        .live-workspace-monitor__file-list code { overflow-wrap: anywhere; font-size: 10.5px; }
        .live-workspace-monitor__browser-controls { color: ${C.textMuted}; font-size: 8px; letter-spacing: 2px; white-space: nowrap; }
        .live-workspace-monitor__address { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 5px 9px; border: 1px solid ${C.border}; border-radius: 7px; background: #080c11; color: ${C.textSub}; }
        .live-workspace-monitor__rail { min-width: 0; background: #0b0f14; }
        .live-workspace-monitor__rail-heading { display: flex; align-items: center; min-height: 40px; padding: 6px 10px; border-bottom: 1px solid ${C.border}; color: ${C.textMuted}; font: 700 9px/1 monospace; letter-spacing: .09em; }
        .live-workspace-monitor__rail-heading strong { margin-left: auto; color: ${C.text}; }
        .live-workspace-monitor__rail ol { list-style: none; margin: 0; padding: 6px; display: grid; gap: 5px; }
        .live-workspace-monitor__rail li button { width: 100%; min-height: 48px; display: grid; grid-template-columns: 18px minmax(0,1fr) auto; align-items: center; gap: 6px; padding: 6px 7px; border: 1px solid ${C.border}; border-radius: 7px; background: #090d12; color: ${C.textSub}; cursor: pointer; text-align: left; }
        .live-workspace-monitor__rail-copy { min-width: 0; }
        .live-workspace-monitor__rail-copy strong { display: block; overflow: hidden; text-overflow: ellipsis; color: ${C.text}; font: 600 9.5px/1.2 monospace; }
        .live-workspace-monitor__rail-copy small { display: block; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: ${C.textMuted}; font: 9px/1.2 monospace; }
        .live-workspace-monitor__rail code { color: ${C.textMuted}; font-size: 8px; }
        .live-workspace-monitor__rail-empty { margin: 0; padding: 16px 10px; color: ${C.textMuted}; font-size: 10.5px; line-height: 1.5; }
        .live-workspace-monitor__truth-footer { padding: 8px 10px; border-top: 1px solid ${C.border}; color: ${C.amber}; background: #0d1218; font-size: 10px; line-height: 1.45; text-align: center; }
        @media (max-width: 840px) {
          .live-workspace-monitor__layout { grid-template-columns: 1fr; }
          .live-workspace-monitor__main { border-right: 0; }
          .live-workspace-monitor__rail { border-top: 1px solid ${C.border}; }
          .live-workspace-monitor__rail ol { grid-template-columns: repeat(2, minmax(0,1fr)); }
        }
        @media (max-width: 560px) {
          .live-workspace-monitor__chrome { align-items: flex-start; flex-wrap: wrap; }
          .live-workspace-monitor__authority-badge { order: 3; }
          .live-workspace-monitor__tab { min-width: 82px; }
          .live-workspace-monitor__layout { min-height: 260px; }
          .live-workspace-monitor__surface { min-height: 230px; }
          .live-workspace-monitor__rail ol { grid-template-columns: 1fr; }
          .live-workspace-monitor__metadata-grid { flex-direction: column; align-items: stretch; }
        }
      `}</style>

      <header className="live-workspace-monitor__chrome">
        <span aria-hidden="true" style={{ color: C.textMuted, fontFamily: 'monospace', letterSpacing: 2 }}>● ● ●</span>
        <div className="live-workspace-monitor__title">
          <strong>LIVE WORKSPACE MONITOR</strong>
          <small>
            Attempt {shortIdentity(latest?.attemptId, 16)} · Workspace {shortIdentity(latest?.workspaceId ?? job?.workspaceId, 16)} · Head {shortIdentity(latest?.repositoryHead, 12)}
          </small>
        </div>
        <span className="live-workspace-monitor__authority-badge">
          <span aria-hidden="true">◉</span> BEOBACHTUNG, NICHT EVIDENCE-AUTHORITY
        </span>
        <MetaPill label="Runtime" value={job?.status ?? 'nicht gebunden'} />
      </header>

      <DesktopFramePane stream={desktopStream} job={job} />

      <div role="tablist" aria-label="Runtime-Beobachtungen" className="live-workspace-monitor__tabs">
        {MONITOR_TABS.map((tab) => {
          const available = projectionMap.has(tab.kind);
          const selected = selectedKind === tab.kind;
          return (
            <button
              key={tab.kind}
              id={`${monitorId}-${tab.kind}-tab`}
              type="button"
              role="tab"
              className="live-workspace-monitor__tab"
              aria-selected={selected}
              aria-controls={`${monitorId}-panel`}
              disabled={!available}
              onClick={() => setSelectedKind(tab.kind)}
            >
              <span aria-hidden="true">{tab.icon}</span> {tab.label}
            </button>
          );
        })}
      </div>

      <div className="live-workspace-monitor__layout">
        <div className="live-workspace-monitor__main">
          <div className="live-workspace-monitor__pane-header">
            <strong>{selectedProjection?.projectionKind ?? 'NO PROJECTION'}</strong>
            <span>{selectedProjection ? `${selectedProjection.sourceKind} · ${shortIdentity(selectedProjection.actionId, 16)}` : 'Kein aktuelles Event'}</span>
            {selectedState ? (
              <span className="live-workspace-monitor__state" style={{ color: selectedState.color }} title={selectedState.description}>
                <span aria-hidden="true">{selectedState.icon}</span> {selectedState.label}
              </span>
            ) : null}
          </div>
          <div
            id={`${monitorId}-panel`}
            role="tabpanel"
            aria-labelledby={selectedKind ? `${monitorId}-${selectedKind}-tab` : undefined}
          >
            <ProjectionPane projection={selectedProjection} />
          </div>
        </div>
        <ObservationRail projections={current} selectedKind={selectedKind} onSelect={setSelectedKind} />
      </div>

      <footer className="live-workspace-monitor__truth-footer">
        Sichtbar auf dem Monitor ≠ Effekt verifiziert. Separate Receipts und Zielsystem-Readbacks entscheiden Evidence und Abschluss.
      </footer>
    </section>
  );
}
