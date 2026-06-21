import React, { useEffect, useMemo, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { getSovereignContainerContract } from './features/product/runtime/sovereignContainerContracts';
import { SOVEREIGN_ACTION_MONITOR_TOGGLE } from './features/product/runtime/sovereignActionContracts';
import type { SovereignTelemetryEvent } from './features/product/runtime/sovereignTelemetry';

type CoachLamp = 'green' | 'yellow' | 'red';

type RuntimeCoachState = {
  lamp: CoachLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source: string;
  updatedAt: number;
};

type GlobalRuntimeWindow = Window & typeof globalThis & {
  __sovereignGlobalRuntimeMonitorInstalled?: boolean;
  __sovereignGlobalRuntimeMonitorRoot?: Root;
  __sovereignRuntimeCoachState?: RuntimeCoachState;
  __sovereignTelemetryEvents?: SovereignTelemetryEvent[];
};

const HOST_ID = 'sovereign-global-runtime-monitor-root';
const MAX_LOG_ENTRIES = 24;
const monitorContainerContract = getSovereignContainerContract('global-runtime-monitor');

function defaultCoachState(): RuntimeCoachState {
  return {
    lamp: 'yellow',
    title: 'Sovereign bereit',
    message: 'Repo laden, Auftrag analysieren und danach Auftrag starten.',
    action: 'Repo oder Builder prüfen',
    thinking: false,
    source: 'runtime-shell',
    updatedAt: Date.now(),
  };
}

function formatTime(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '--:--:--';
  return new Date(value).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function lampClassName(lamp: CoachLamp): string {
  if (lamp === 'red') return 'sovereign-status-dot sovereign-status-dot-red';
  if (lamp === 'yellow') return 'sovereign-status-dot sovereign-status-dot-yellow';
  return 'sovereign-status-dot sovereign-status-dot-green';
}

function telemetryLevelLamp(level: SovereignTelemetryEvent['level']): CoachLamp {
  if (level === 'error') return 'red';
  if (level === 'warning') return 'yellow';
  return 'green';
}

function compactTelemetry(event: SovereignTelemetryEvent): RuntimeCoachState {
  return {
    lamp: telemetryLevelLamp(event.level),
    title: event.label,
    message: event.message,
    action: event.stage,
    thinking: event.level === 'info',
    source: event.stage,
    updatedAt: event.timestamp,
  };
}

function appendUnique(entries: RuntimeCoachState[], entry: RuntimeCoachState): RuntimeCoachState[] {
  const previous = entries[0];
  if (previous && previous.title === entry.title && previous.message === entry.message && previous.action === entry.action) {
    return entries;
  }
  return [entry, ...entries].slice(0, MAX_LOG_ENTRIES);
}

function seedLog(win: GlobalRuntimeWindow): RuntimeCoachState[] {
  const coach = win.__sovereignRuntimeCoachState ?? defaultCoachState();
  const telemetry = Array.isArray(win.__sovereignTelemetryEvents)
    ? win.__sovereignTelemetryEvents.slice(-8).reverse().map(compactTelemetry)
    : [];
  return [coach, ...telemetry].slice(0, MAX_LOG_ENTRIES);
}

function GlobalRuntimeMonitor(): React.ReactElement {
  const [coachState, setCoachState] = useState<RuntimeCoachState>(() => {
    if (typeof window === 'undefined') return defaultCoachState();
    return (window as GlobalRuntimeWindow).__sovereignRuntimeCoachState ?? defaultCoachState();
  });
  const [log, setLog] = useState<RuntimeCoachState[]>(() => {
    if (typeof window === 'undefined') return [defaultCoachState()];
    return seedLog(window as GlobalRuntimeWindow);
  });
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const handleCoachState = (event: Event): void => {
      const detail = (event as CustomEvent<RuntimeCoachState>).detail;
      if (!detail || !detail.title || !detail.message) return;
      setCoachState(detail);
      setLog((current) => appendUnique(current, detail));
    };

    const handleTelemetry = (event: Event): void => {
      const detail = (event as CustomEvent<SovereignTelemetryEvent>).detail;
      if (!detail || !detail.label || !detail.message) return;
      setLog((current) => appendUnique(current, compactTelemetry(detail)));
    };

    window.addEventListener('sovereign:runtime-coach-state', handleCoachState as EventListener);
    window.addEventListener('sovereign:telemetry-event', handleTelemetry as EventListener);

    return () => {
      window.removeEventListener('sovereign:runtime-coach-state', handleCoachState as EventListener);
      window.removeEventListener('sovereign:telemetry-event', handleTelemetry as EventListener);
    };
  }, []);

  const visibleLog = useMemo(() => log.slice(0, expanded ? MAX_LOG_ENTRIES : 5), [expanded, log]);

  return (
    <section
      className={monitorContainerContract.rootClass}
      data-role={monitorContainerContract.dataRole}
      data-testid={monitorContainerContract.testId}
      aria-label={monitorContainerContract.ariaLabel}
    >
      <div className="sovereign-monitor-head">
        <div>
          <div className="sovereign-eyebrow">Coach · Live Log · Aktionen</div>
          <h2>Agenten-Monitor · Sovereign Bot</h2>
        </div>
        <button
          type="button"
          className="sovereign-monitor-toggle"
          onClick={() => setExpanded((value) => !value)}
          data-role={SOVEREIGN_ACTION_MONITOR_TOGGLE.dataRole}
          data-testid={SOVEREIGN_ACTION_MONITOR_TOGGLE.testId}
          aria-label={SOVEREIGN_ACTION_MONITOR_TOGGLE.ariaLabel}
          data-state="idle"
        >
          {expanded ? 'Log einklappen' : 'Log anzeigen'}
        </button>
      </div>

      <div className="sovereign-monitor-status">
        <span className={lampClassName(coachState.lamp)} />
        <div className="sovereign-monitor-copy">
          <strong>{coachState.title}</strong>
          <span>{formatTime(coachState.updatedAt)} · {coachState.source} · {coachState.thinking ? 'arbeitet' : 'bereit'}</span>
          <p>{coachState.message}</p>
          <em>Next Action: {coachState.action}</em>
        </div>
      </div>

      {expanded ? (
        <div className="sovereign-monitor-log" data-testid="global-runtime-monitor-log">
          {visibleLog.map((entry, index) => (
            <div key={`${entry.updatedAt}-${entry.title}-${index}`} className="sovereign-monitor-line">
              <span className={lampClassName(entry.lamp)} />
              <div>
                <span>{formatTime(entry.updatedAt)} · {entry.source}</span>
                <p>{entry.title}: {entry.message}</p>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function installGlobalRuntimeMonitor(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const win = window as GlobalRuntimeWindow;
  if (win.__sovereignGlobalRuntimeMonitorInstalled) return;

  const appRoot = document.getElementById('root');
  const host = document.getElementById(HOST_ID) ?? document.createElement('div');
  host.id = HOST_ID;

  if (!host.parentElement) {
    document.body.insertBefore(host, appRoot ?? document.body.firstChild);
  }

  win.__sovereignGlobalRuntimeMonitorInstalled = true;
  win.__sovereignGlobalRuntimeMonitorRoot = createRoot(host);
  win.__sovereignGlobalRuntimeMonitorRoot.render(<GlobalRuntimeMonitor />);
}
