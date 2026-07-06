import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { maskSecrets } from './shared/utils/crypto';
import { getSovereignContainerContract } from './features/product/runtime/sovereignContainerContracts';
import { SOVEREIGN_ACTION_MONITOR_TOGGLE } from './features/product/runtime/sovereignActionContracts';
import { deriveReleaseGuideState, type ReleaseGuideTab } from './features/product/runtime/sovereignReleaseGuide';
import { SOVEREIGN_WORKSPACE_COMMAND_EVENT } from './features/product/runtime/sovereignWorkspaceCommand';
import type { SovereignTelemetryEvent } from './features/product/runtime/sovereignTelemetry';

type CoachLamp = 'green' | 'yellow' | 'red';
type RuntimeCoachState = { lamp: CoachLamp; title: string; message: string; action: string; thinking: boolean; source: string; updatedAt: number };
type ReleaseGuideCommand = { type: 'back' | 'confirm' | 'next'; targetTab: ReleaseGuideTab | null };
type GlobalRuntimeWindow = Window & typeof globalThis & { __sovereignGlobalRuntimeMonitorInstalled?: boolean; __sovereignGlobalRuntimeMonitorRoot?: Root; __sovereignRuntimeCoachState?: RuntimeCoachState; __sovereignTelemetryEvents?: SovereignTelemetryEvent[] };
type StepState = 'done' | 'current' | 'waiting' | 'halted';
type Step = { index: number; label: string; state: StepState };
type StepPlan = { current: number; total: number; label: string; steps: Step[] };
type LogFilter = 'all' | 'error' | 'warning' | 'info';

const HOST_ID = 'sovereign-global-runtime-monitor-root';
const MAX_LOG_ENTRIES = 24;
const AUTO_ADVANCE_DELAY_MS = 1500;
const monitorContainerContract = getSovereignContainerContract('global-runtime-monitor');
const monitorToggleContract = SOVEREIGN_ACTION_MONITOR_TOGGLE;

function defaultCoachState(): RuntimeCoachState {
  return { lamp: 'yellow', title: 'Sovereign bereit', message: 'Repo laden, Auftrag analysieren und danach Auftrag starten.', action: 'Repo oder Builder prüfen', thinking: false, source: 'runtime-shell', updatedAt: Date.now() };
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

function logFilterLabel(filter: LogFilter): string {
  if (filter === 'error') return 'Fehler';
  if (filter === 'warning') return 'Warnung';
  if (filter === 'info') return 'Info';
  return 'Alle';
}

function filterLogEntry(entry: RuntimeCoachState, filter: LogFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'error') return entry.lamp === 'red';
  if (filter === 'warning') return entry.lamp === 'yellow';
  return entry.lamp === 'green';
}

function coachText(coach: RuntimeCoachState): string {
  return `${coach.title} ${coach.message} ${coach.action} ${coach.source}`.toLowerCase();
}

function hasBlockingToken(coach: RuntimeCoachState): boolean {
  return [
    'guard',
    'health',
    'validation_failed',
    'blocked',
    'blockiert',
    'failed',
    'fehler',
    'draft pr',
    'pull request',
    'workflow',
    'package-build',
    'package build',
    'publishing',
  ].some((token) => coachText(coach).includes(token));
}

function canAutoAdvanceGuide(coach: RuntimeCoachState, targetTab: ReleaseGuideTab | null): targetTab is ReleaseGuideTab {
  void coach;
  void targetTab;
  return false;
}

function showRepairPanel(coach: RuntimeCoachState): boolean {
  const source = coachText(coach);
  return coach.lamp === 'red' && ['health', 'guard', 'validation_failed', 'failed', 'blockiert'].some((token) => source.includes(token));
}

function compactTelemetry(event: SovereignTelemetryEvent): RuntimeCoachState {
  return { lamp: telemetryLevelLamp(event.level), title: event.label, message: event.message, action: event.stage, thinking: event.level === 'info', source: event.stage, updatedAt: event.timestamp };
}

function appendUnique(entries: RuntimeCoachState[], entry: RuntimeCoachState): RuntimeCoachState[] {
  const previous = entries[0];
  if (previous && previous.title === entry.title && previous.message === entry.message && previous.action === entry.action) return entries;
  return [entry, ...entries].slice(0, MAX_LOG_ENTRIES);
}

function seedLog(win: GlobalRuntimeWindow): RuntimeCoachState[] {
  const coach = win.__sovereignRuntimeCoachState ?? defaultCoachState();
  const telemetry = Array.isArray(win.__sovereignTelemetryEvents) ? win.__sovereignTelemetryEvents.slice(-8).reverse().map(compactTelemetry) : [];
  return [coach, ...telemetry].slice(0, MAX_LOG_ENTRIES);
}

function publishGuideCommand(command: ReleaseGuideCommand): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(SOVEREIGN_WORKSPACE_COMMAND_EVENT, { detail: command }));
}

function compactLabel(entry: RuntimeCoachState): string {
  const title = entry.title.trim();
  if (title.length > 0) return title.length > 34 ? `${title.slice(0, 31)}...` : title;
  const action = entry.action.trim();
  return action.length > 0 ? action : entry.source;
}

function stepPlan(coach: RuntimeCoachState, log: RuntimeCoachState[]): StepPlan {
  const chronological = [...log].reverse();
  const labels: string[] = [];

  for (const entry of chronological) {
    const label = compactLabel(entry);
    if (!label || labels[labels.length - 1] === label) continue;
    labels.push(label);
  }

  const currentLabel = compactLabel(coach);
  if (currentLabel && labels[labels.length - 1] !== currentLabel) labels.push(currentLabel);

  const visibleLabels = labels.slice(-8);
  const total = Math.max(1, visibleLabels.length);
  const current = total;
  const fallbackState: StepState = coach.lamp === 'red' ? 'halted' : 'current';
  const steps: Step[] = visibleLabels.length > 0
    ? visibleLabels.map((label, offset): Step => ({
      index: offset + 1,
      label,
      state: offset + 1 < total ? 'done' : fallbackState,
    }))
    : [{ index: 1, label: currentLabel || 'Runtime wartet', state: fallbackState }];

  return { current, total, label: `${current}/${total} · ${steps[steps.length - 1]?.label ?? 'Runtime'}`, steps };
}

function stepClassName(state: StepState): string {
  if (state === 'done') return 'rounded bg-emerald-500/30 px-2 py-1 text-emerald-100';
  if (state === 'current') return 'rounded bg-cyan-500/30 px-2 py-1 text-cyan-100';
  if (state === 'halted') return 'rounded bg-rose-500/30 px-2 py-1 text-rose-100';
  return 'rounded bg-slate-800 px-2 py-1 text-slate-400';
}

function GlobalRuntimeMonitor(): React.ReactElement {
  const [coachState, setCoachState] = useState<RuntimeCoachState>(() => typeof window === 'undefined' ? defaultCoachState() : (window as GlobalRuntimeWindow).__sovereignRuntimeCoachState ?? defaultCoachState());
  const [log, setLog] = useState<RuntimeCoachState[]>(() => typeof window === 'undefined' ? [defaultCoachState()] : seedLog(window as GlobalRuntimeWindow));
  const [confirmedAt, setConfirmedAt] = useState<number | null>(null);
  const [monitorVisible, setMonitorVisible] = useState(true);
  const guide = useMemo(() => deriveReleaseGuideState(coachState), [coachState]);
  const plan = useMemo(() => stepPlan(coachState, log), [coachState, log]);
  const [logFilter, setLogFilter] = useState<LogFilter>('all');
  const [autoAdvanceRemaining, setAutoAdvanceRemaining] = useState<number | null>(null);
  const logViewportRef = useRef<HTMLDivElement | null>(null);
  const lastAutoCommandKeyRef = useRef('');
  const visibleLog = useMemo(() => log.filter((entry) => filterLogEntry(entry, logFilter)).slice(0, MAX_LOG_ENTRIES), [log, logFilter]);
  const autoAdvanceSafe = canAutoAdvanceGuide(coachState, guide.targetTab);
  const repairPanelVisible = showRepairPanel(coachState);

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
    if (!logViewportRef.current) return;
    logViewportRef.current.scrollTop = 0;
  }, [visibleLog.length, logFilter]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    setAutoAdvanceRemaining(null);

    if (!autoAdvanceSafe) return undefined;

    const targetTab = guide.targetTab;
    const commandKey = `${coachState.updatedAt}:${coachState.title}:${targetTab}`;
    if (!targetTab || lastAutoCommandKeyRef.current === commandKey) return undefined;

    setAutoAdvanceRemaining(AUTO_ADVANCE_DELAY_MS / 1000);
    const tick = window.setInterval(() => {
      setAutoAdvanceRemaining((current) => {
        if (current === null) return null;
        return Math.max(0, Number((current - 0.5).toFixed(1)));
      });
    }, 500);
    const timer = window.setTimeout(() => {
      lastAutoCommandKeyRef.current = commandKey;
      setAutoAdvanceRemaining(null);
      publishGuideCommand({ type: 'next', targetTab });
    }, AUTO_ADVANCE_DELAY_MS);

    return () => {
      window.clearInterval(tick);
      window.clearTimeout(timer);
    };
  }, [autoAdvanceSafe, coachState.title, coachState.updatedAt, guide.targetTab]);

  // The monitor is a truth/display surface. It may auto-focus harmless UI tabs only;
  // guarded runtime actions, health gates, workflow steps and PR publishing still require visible user intent.

  const confirmStep = (): void => {
    const now = Date.now();
    setConfirmedAt(now);
    publishGuideCommand({ type: 'confirm', targetTab: guide.targetTab });
    setLog((current) => appendUnique(current, { lamp: 'green', title: 'Schritt bestätigt', message: guide.targetTab ? `Bestätigt. Ich markiere ${guide.targetTab} als nächsten sicheren Bereich.` : 'Bestätigt. Ich warte auf den nächsten sicheren Schritt.', action: guide.nextEnabled ? guide.nextLabel : 'Weiter beobachten', thinking: false, source: 'release-guide', updatedAt: now }));
  };

  return (
    <section className={monitorContainerContract.rootClass} data-role={monitorContainerContract.dataRole} data-testid={monitorContainerContract.testId} aria-label={monitorContainerContract.ariaLabel}>
      <div className="sovereign-monitor-head">
        <div className="sovereign-helper-title-row"><span className="sovereign-helper-avatar" aria-hidden="true">{guide.mood}</span><div><div className="sovereign-eyebrow">Coach · Live Log · Systemspur</div><h2>Agenten-Monitor · Sovereign Helper</h2><p className="sovereign-helper-subtitle">{guide.helperTitle}</p></div></div>
        <button type="button" className="sovereign-monitor-toggle" onClick={() => setMonitorVisible((prev) => !prev)} data-testid={monitorToggleContract.testId} data-role={monitorToggleContract.dataRole} aria-label={monitorToggleContract.ariaLabel} aria-pressed={monitorVisible}>{monitorVisible ? '▲' : '▼'}</button>
        <span className="sovereign-monitor-pill" data-state="single-window">Spiegelt Runtime</span>
      </div>
      {monitorVisible && <div className="sovereign-monitor-body">
        {/* ✅ SECURITY: Mask coachState values in the global monitor for protection against credential leakage. */}
        <div className="sovereign-monitor-status"><span className={lampClassName(coachState.lamp)} /><div className="sovereign-monitor-copy"><strong>{maskSecrets(coachState.title)}</strong><span>{formatTime(coachState.updatedAt)} · {coachState.source} · {coachState.thinking ? 'arbeitet' : 'bereit'}</span><p>{maskSecrets(coachState.message)}</p><em>Next Action: {maskSecrets(coachState.action)}</em></div></div>
        <div className="sovereign-helper-panel" data-testid="release-guide__panel">
          <div className="sovereign-helper-copy"><strong>{maskSecrets(guide.helperMessage)}</strong><span>{confirmedAt ? `Zuletzt bestätigt: ${formatTime(confirmedAt)}` : (maskSecrets(guide.waitingReason) || 'Der sichtbare Weiter-Button bleibt deine bewusste Aktion.')}</span>{autoAdvanceRemaining !== null ? <span className="sovereign-auto-advance-hint">Auto-Fokus in {autoAdvanceRemaining.toFixed(1)}s · nur UI-Navigation</span> : null}</div>
          {repairPanelVisible ? <div className="sovereign-health-repair-panel" data-testid="release-guide__repair-panel"><strong>Nächste sichere Reparatur</strong><span>Health/Guard blockiert bewusst. Öffne Diagnose oder Reparatur, statt plan-only Output zu erzwingen.</span><div><button type="button" onClick={() => publishGuideCommand({ type: 'next', targetTab: 'telemetry' })}>Telemetry</button><button type="button" onClick={() => publishGuideCommand({ type: 'next', targetTab: 'health' })}>Health</button><button type="button" onClick={() => publishGuideCommand({ type: 'next', targetTab: 'repair' })}>Repair</button></div></div> : null}<div className="sovereign-monitor-progress" data-testid="release-guide__progress" aria-label={`Arbeitsstand ${plan.label}`}><div className="sovereign-monitor-progress-head"><span>Arbeitsstand</span><strong>{plan.label}</strong></div><div className="grid gap-1 text-[10px]" style={{ gridTemplateColumns: `repeat(${plan.total}, minmax(0, 1fr))` }}>{plan.steps.map((step) => <span key={step.index} className={stepClassName(step.state)} title={step.label}>{step.index}. {step.label}</span>)}</div></div>
        </div>
      </div>}
      {monitorVisible ? <div className="sovereign-guide-actions" data-testid="release-guide__actions"><button className="sovereign-guide-button" type="button" onClick={() => publishGuideCommand({ type: 'back', targetTab: guide.previousTab })} data-testid="release-guide__back">Zurück</button><button className="sovereign-guide-button" type="button" onClick={confirmStep} data-testid="release-guide__confirm">{guide.confirmLabel}</button><button className="sovereign-guide-button sovereign-guide-button-primary" type="button" onClick={() => publishGuideCommand({ type: 'next', targetTab: guide.targetTab })} disabled={!guide.nextEnabled} aria-disabled={!guide.nextEnabled} data-testid="release-guide__next">{guide.nextLabel}</button></div> : null}
      <div className="sovereign-monitor-log-shell"><div className="sovereign-monitor-filter-row" aria-label="Logfilter">{(['all', 'error', 'warning', 'info'] as LogFilter[]).map((filter) => <button key={filter} type="button" onClick={() => setLogFilter(filter)} data-state={logFilter === filter ? 'active' : 'idle'}>{logFilterLabel(filter)}</button>)}</div><div ref={logViewportRef} className="sovereign-monitor-log" data-testid="global-runtime-monitor-log">{visibleLog.map((entry, index) => <div key={`${entry.updatedAt}-${entry.title}-${index}`} className="sovereign-monitor-line"><span className={lampClassName(entry.lamp)} /><div><span>{formatTime(entry.updatedAt)} · {entry.source}</span><p>{maskSecrets(entry.title)}: {maskSecrets(entry.message)}</p></div></div>)}</div></div>
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
  if (!host.parentElement) document.body.insertBefore(host, appRoot ?? document.body.firstChild);
  win.__sovereignGlobalRuntimeMonitorInstalled = true;
  win.__sovereignGlobalRuntimeMonitorRoot = createRoot(host);
  win.__sovereignGlobalRuntimeMonitorRoot.render(<GlobalRuntimeMonitor />);
}
