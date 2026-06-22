import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { getSovereignContainerContract } from './features/product/runtime/sovereignContainerContracts';
import { getSovereignActionContract } from './features/product/runtime/sovereignActionContracts';
import {
  deriveReleaseGuideState,
  type ReleaseGuideTab,
} from './features/product/runtime/sovereignReleaseGuide';
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

type ReleaseGuideCommand = {
  type: 'back' | 'confirm' | 'next';
  targetTab: ReleaseGuideTab | null;
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
const monitorToggleContract = getSovereignActionContract('monitor-toggle');

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

function publishGuideCommand(command: ReleaseGuideCommand): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('sovereign:release-guide-command', { detail: command }));
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
  const [confirmedAt, setConfirmedAt] = useState<number | null>(null);
  const [monitorVisible, setMonitorVisible] = useState(true);
  const lastAutoCommandKeyRef = useRef('');

  const guide = useMemo(() => deriveReleaseGuideState(coachState), [coachState]);

  const toggleMonitor = (): void => {
    setMonitorVisible((prev) => !prev);
  };

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

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    if (!guide.nextEnabled || !guide.targetTab) return undefined;

    const commandKey = `${guide.targetTab}:${coachState.title}:${coachState.action}:${coachState.updatedAt}`;
    if (lastAutoCommandKeyRef.current === commandKey) return undefined;
    lastAutoCommandKeyRef.current = commandKey;

    const handle = window.setTimeout(() => {
      publishGuideCommand({ type: 'next', targetTab: guide.targetTab });
    }, 180);

    return () => window.clearTimeout(handle);
  }, [coachState.action, coachState.title, coachState.updatedAt, guide.nextEnabled, guide.targetTab]);

  const visibleLog = useMemo(() => log.slice(0, MAX_LOG_ENTRIES), [log]);

  const confirmStep = (): void => {
    const now = Date.now();
    setConfirmedAt(now);
    publishGuideCommand({ type: 'confirm', targetTab: guide.targetTab });
    setLog((current) => appendUnique(current, {
      lamp: 'green',
      title: 'Schritt bestätigt',
      message: guide.targetTab
        ? `Bestätigt. Ich markiere ${guide.targetTab} als nächsten sicheren Bereich.`
        : 'Bestätigt. Ich warte auf den nächsten sicheren Schritt.',
      action: guide.nextEnabled ? guide.nextLabel : 'Weiter beobachten',
      thinking: false,
      source: 'release-guide',
      updatedAt: now,
    }));
  };

  return (
    <section
      className={monitorContainerContract.rootClass}
      data-role={monitorContainerContract.dataRole}
      data-testid={monitorContainerContract.testId}
      aria-label={monitorContainerContract.ariaLabel}
    >
      <div className="sovereign-monitor-head">
        <div className="sovereign-helper-title-row">
          <span className="sovereign-helper-avatar" aria-hidden="true">{guide.mood}</span>
          <div>
            <div className="sovereign-eyebrow">Coach · Live Log · drei Aktionen</div>
            <h2>Agenten-Monitor · Sovereign Helper</h2>
            <p className="sovereign-helper-subtitle">{guide.helperTitle}</p>
          </div>
        </div>
        <button
          type="button"
          className="sovereign-monitor-toggle"
          onClick={toggleMonitor}
          data-testid={monitorToggleContract.testId}
          data-role={monitorToggleContract.dataRole}
          aria-label={monitorToggleContract.ariaLabel}
          aria-pressed={monitorVisible}
        >
          {monitorVisible ? '▲' : '▼'}
        </button>
        <span className="sovereign-monitor-pill" data-state="single-window">
          Arbeitet automatisch
        </span>
      </div>

      {monitorVisible && (
        <div className="sovereign-monitor-body">
          <div className="sovereign-monitor-status">
            <span className={lampClassName(coachState.lamp)} />
            <div className="sovereign-monitor-copy">
              <strong>{coachState.title}</strong>
              <span>{formatTime(coachState.updatedAt)} · {coachState.source} · {coachState.thinking ? 'arbeitet' : 'bereit'}</span>
              <p>{coachState.message}</p>
              <em>Next Action: {coachState.action}</em>
            </div>
          </div>

          <div className="sovereign-helper-panel" data-testid="release-guide__panel">
            <div className="sovereign-helper-copy">
              <strong>{guide.helperMessage}</strong>
              <span>{confirmedAt ? `Zuletzt bestätigt: ${formatTime(confirmedAt)}` : guide.waitingReason || 'Ich leite den nächsten sicheren Schritt automatisch ein.'}</span>
            </div>
            <div className="sovereign-monitor-progress" data-testid="release-guide__progress" aria-label={`Arbeitsfortschritt ${guide.progress}%`}>
              <div className="sovereign-monitor-progress-head">
                <span>Arbeitsfortschritt</span>
                <strong>{guide.progressLabel}</strong>
              </div>
              <div className="sovereign-monitor-progress-track">
                <div className="sovereign-monitor-progress-fill" style={{ width: `${guide.progress}%` }} />
              </div>
            </div>
            <div className="sovereign-guide-actions" data-testid="release-guide__actions">
              <button
                className="sovereign-guide-button"
                type="button"
                onClick={() => publishGuideCommand({ type: 'back', targetTab: guide.previousTab })}
                data-testid="release-guide__back"
              >
                Zurück
              </button>
              <button className="sovereign-guide-button" type="button" onClick={confirmStep} data-testid="release-guide__confirm">
                {guide.confirmLabel}
              </button>
              <button
                className="sovereign-guide-button sovereign-guide-button-primary"
                type="button"
                onClick={() => publishGuideCommand({ type: 'next', targetTab: guide.targetTab })}
                disabled={!guide.nextEnabled}
                aria-disabled={!guide.nextEnabled}
                data-testid="release-guide__next"
              >
                {guide.nextLabel}
              </button>
            </div>
          </div>
        </div>
      )}

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
