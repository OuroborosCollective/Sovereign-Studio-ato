import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import App from './App';

type ModuleId =
  | 'init'
  | 'router'
  | 'pattern'
  | 'sync'
  | 'orchestr'
  | 'session'
  | 'logger'
  | 'restore';

type WorkspaceTab =
  | 'builder'
  | 'repo'
  | 'files'
  | 'diff'
  | 'workflow'
  | 'repair'
  | 'remote'
  | 'memory'
  | 'telemetry'
  | 'monitor'
  | 'health'
  | 'runtime'
  | 'coverage'
  | 'findings';

type Signal = 'idle' | 'active' | 'processing' | 'warning' | 'error';
type Phase = 'idle' | 'spinup' | 'working' | 'done' | 'error';
type ConditionStatus = 'pass' | 'fail' | 'wait';

interface PublishedRuntimeSnapshot {
  repoReady: boolean;
  setupPhase: 'no-repo' | 'repo-loading' | 'repo-loaded' | 'repo-error';
  isBusy: boolean;
  status: string;
  dependencyHealthy: boolean;
  updatedAt: number;
}

interface RuntimeCondition {
  label: string;
  status: ConditionStatus;
}

interface RuntimeModule {
  id: ModuleId;
  signal: Signal;
  phase: Phase;
  detail: string;
  conditions: RuntimeCondition[];
}

interface RuntimeLogLine {
  level: 'info' | 'warn' | 'error' | 'signal';
  moduleId: ModuleId;
  message: string;
}

interface RuntimeFrameState {
  activeModuleId: ModuleId;
  modules: RuntimeModule[];
  logs: RuntimeLogLine[];
  signalSummary: string;
  sessionSummary: string;
  overrideActive: boolean;
}

interface WorkspaceMenuItem {
  id: WorkspaceTab;
  label: string;
  hint: string;
  group: 'primary' | 'work' | 'ops';
}

type SovereignWindow = Window & {
  __sovereignSetupState?: unknown;
};

const SIGNAL_COLOR: Record<Signal, string> = {
  idle: '#30363d',
  active: '#3fb950',
  processing: '#58a6ff',
  warning: '#d29922',
  error: '#f85149',
};

const WORKSPACE_MENU: WorkspaceMenuItem[] = [
  { id: 'builder', label: 'Chat', hint: 'Hauptfläche', group: 'primary' },
  { id: 'repo', label: 'Repo', hint: 'Quelle', group: 'primary' },
  { id: 'files', label: 'Files', hint: 'Review', group: 'primary' },
  { id: 'diff', label: 'Diff', hint: 'Änderungen', group: 'primary' },
  { id: 'workflow', label: 'Workflow', hint: 'CI Watch', group: 'work' },
  { id: 'repair', label: 'Repair', hint: 'Fixplan', group: 'work' },
  { id: 'remote', label: 'Remote', hint: 'Memory', group: 'work' },
  { id: 'monitor', label: 'Monitor', hint: 'Live', group: 'work' },
  { id: 'telemetry', label: 'Telemetry', hint: 'Events', group: 'ops' },
  { id: 'health', label: 'Health', hint: 'Status', group: 'ops' },
  { id: 'runtime', label: 'Runtime', hint: 'Steps', group: 'ops' },
  { id: 'coverage', label: 'Coverage', hint: 'Gates', group: 'ops' },
  { id: 'findings', label: 'Findings', hint: 'Scanner', group: 'ops' },
  { id: 'memory', label: 'Pattern', hint: 'Lernen', group: 'ops' },
];

function normalizeSetupPhase(value: unknown): PublishedRuntimeSnapshot['setupPhase'] {
  if (
    value === 'no-repo'
    || value === 'repo-loading'
    || value === 'repo-loaded'
    || value === 'repo-error'
  ) {
    return value;
  }

  return 'no-repo';
}

function readPublishedRuntimeSnapshot(value: unknown): PublishedRuntimeSnapshot | null {
  if (!value || typeof value !== 'object') return null;

  const record = value as Record<string, unknown>;

  return {
    repoReady: record.repoReady === true,
    setupPhase: normalizeSetupPhase(record.setupPhase),
    isBusy: record.isBusy === true,
    status: typeof record.status === 'string' && record.status.trim()
      ? record.status.trim()
      : 'Waiting for runtime publication.',
    dependencyHealthy: record.dependencyHealthy === true,
    updatedAt: typeof record.updatedAt === 'number' ? record.updatedAt : 0,
  };
}

function phaseFor(signal: Signal): Phase {
  if (signal === 'error') return 'error';
  if (signal === 'processing') return 'working';
  if (signal === 'active') return 'done';
  if (signal === 'warning') return 'spinup';
  return 'idle';
}

function moduleState(
  id: ModuleId,
  signal: Signal,
  detail: string,
  conditions: RuntimeCondition[],
): RuntimeModule {
  return {
    id,
    signal,
    phase: phaseFor(signal),
    detail,
    conditions,
  };
}

function deriveRuntimeFrameState(snapshot: PublishedRuntimeSnapshot | null): RuntimeFrameState {
  const repoSignal: Signal = snapshot?.setupPhase === 'repo-error'
    ? 'error'
    : snapshot?.isBusy
      ? 'processing'
      : snapshot?.repoReady
        ? 'active'
        : 'warning';

  const modules: RuntimeModule[] = [
    moduleState('init', repoSignal, snapshot?.status || 'Waiting for inner App runtime.', [
      { label: 'Inner App published setup state', status: snapshot ? 'pass' : 'wait' },
      { label: 'Repo snapshot ready', status: snapshot?.repoReady ? 'pass' : 'wait' },
      { label: 'Dependency lifecycle healthy', status: snapshot?.dependencyHealthy ? 'pass' : 'wait' },
    ]),
    moduleState('router', snapshot?.isBusy ? 'processing' : 'active', 'Composition wrapper is active. App.tsx stays untouched.', [
      { label: 'Wrapper observes runtime only', status: 'pass' },
      { label: 'Inner App owns routing logic', status: 'pass' },
      { label: 'No simulated auto-switch', status: 'pass' },
    ]),
    moduleState('pattern', 'idle', 'Pattern memory remains inside the existing App runtime.', [
      { label: 'No fabricated pattern count', status: 'pass' },
      { label: 'No wrapper-side pattern mutation', status: 'pass' },
    ]),
    moduleState('sync', 'idle', 'Remote sync remains inside the existing App runtime.', [
      { label: 'Wrapper does not call remote gateway', status: 'pass' },
      { label: 'No hardcoded gateway in wrapper', status: 'pass' },
    ]),
    moduleState('orchestr', snapshot?.isBusy ? 'processing' : 'idle', 'Agent orchestration remains inside the existing App runtime.', [
      { label: 'Wrapper does not start jobs', status: 'pass' },
      { label: 'Runtime work stays in inner App', status: 'pass' },
    ]),
    moduleState('session', snapshot ? 'active' : 'idle', snapshot ? `Runtime publication observed at ${snapshot.updatedAt}.` : 'Waiting for first runtime publication.', [
      { label: 'Session state is observed only', status: snapshot ? 'pass' : 'wait' },
      { label: 'Wrapper does not mutate session', status: 'pass' },
    ]),
    moduleState('logger', snapshot ? 'active' : 'idle', snapshot ? 'Published setup event observed.' : 'No published setup event observed yet.', [
      { label: 'Wrapper logs only derived frame facts', status: 'pass' },
      { label: 'No private setup values rendered', status: 'pass' },
    ]),
    moduleState('restore', 'idle', 'Restore remains an explicit action inside the existing App.', [
      { label: 'Wrapper does not restore automatically', status: 'pass' },
      { label: 'Wrapper does not clear automatically', status: 'pass' },
    ]),
  ];

  const activeModule = modules.find((module) => module.signal === 'error')
    ?? modules.find((module) => module.signal === 'processing')
    ?? modules.find((module) => module.signal === 'warning')
    ?? modules.find((module) => module.signal === 'active')
    ?? modules[0];

  const logs: RuntimeLogLine[] = modules
    .filter((module) => module.signal !== 'idle')
    .map((module) => ({
      level: module.signal === 'error'
        ? 'error'
        : module.signal === 'warning'
          ? 'warn'
          : module.signal === 'processing'
            ? 'signal'
            : 'info',
      moduleId: module.id,
      message: module.detail,
    }));

  return {
    activeModuleId: activeModule.id,
    modules,
    logs,
    signalSummary: `${modules.filter((module) => module.signal === 'processing').length} processing · ${modules.filter((module) => module.signal === 'warning').length} warning · ${modules.filter((module) => module.signal === 'error').length} error`,
    sessionSummary: snapshot
      ? `phase=${snapshot.setupPhase} · repo=${snapshot.repoReady ? 'ready' : 'not-ready'}`
      : 'phase=waiting',
    overrideActive: false,
  };
}

function currentModule(state: RuntimeFrameState): RuntimeModule {
  return state.modules.find((module) => module.id === state.activeModuleId) ?? state.modules[0];
}

function publishWorkspaceCommand(targetTab: WorkspaceTab): void {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(new CustomEvent('sovereign:release-guide-command', {
    detail: {
      type: 'next',
      targetTab,
    },
  }));
}

function RuntimeLamp({ signal }: { signal: Signal }) {
  const color = SIGNAL_COLOR[signal];

  return (
    <span
      aria-hidden="true"
      className="inline-block h-2.5 w-2.5 rounded-full"
      style={{
        background: signal === 'idle' ? '#21262d' : color,
        boxShadow: signal === 'idle' ? 'none' : `0 0 7px ${color}`,
      }}
    />
  );
}

function RuntimePanel({ state, module }: { state: RuntimeFrameState; module: RuntimeModule }) {
  return (
    <div className="border-t border-slate-800 bg-[#0d1117]" data-testid="sovereign-wrapper-runtime-panel">
      <div className="grid h-28 grid-cols-1 gap-2 overflow-hidden p-2 sm:grid-cols-2">
        <div className="overflow-y-auto rounded-md border border-slate-800 bg-black/70 px-2 py-1 font-mono text-[10px] leading-5 text-slate-300">
          {state.logs.length ? state.logs.map((line) => (
            <p key={`${line.moduleId}:${line.level}:${line.message}`}>
              <span className="text-slate-600">[{line.moduleId}]</span>{' '}
              <span>{line.level.toUpperCase()}</span>{' '}
              <span>{line.message}</span>
            </p>
          )) : <p className="text-slate-600">no active runtime signals</p>}
        </div>

        <div className="overflow-y-auto rounded-md border border-slate-800 bg-[#161b22] p-2 font-mono text-[10px] text-slate-400">
          <p className="mb-2 uppercase tracking-[0.18em] text-slate-500">Condition Chain</p>
          {module.conditions.map((condition) => (
            <p key={`${module.id}:${condition.label}`} className="flex justify-between gap-2 border-b border-slate-800 py-1">
              <span className="truncate">{condition.label}</span>
              <span>{condition.status}</span>
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}

function WorkspaceMenu() {
  return (
    <nav
      className="border-t border-slate-900 bg-[#05070b] px-2 py-2"
      aria-label="Sovereign workspace menu bridge"
      data-testid="sovereign-wrapper-workspace-menu"
    >
      <div className="flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {WORKSPACE_MENU.map((item) => (
          <button
            key={item.id}
            type="button"
            className={item.group === 'primary'
              ? 'min-w-[4.8rem] rounded-xl border border-cyan-400/40 bg-cyan-400/10 px-3 py-2 text-left text-[10px] font-bold text-cyan-100'
              : item.group === 'work'
                ? 'min-w-[5.4rem] rounded-xl border border-amber-400/30 bg-amber-400/5 px-3 py-2 text-left text-[10px] font-bold text-amber-100'
                : 'min-w-[5.4rem] rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-left text-[10px] font-bold text-slate-300'}
            onClick={() => publishWorkspaceCommand(item.id)}
            data-testid={`sovereign-wrapper-menu__${item.id}`}
          >
            <span className="block text-[11px] leading-4">{item.label}</span>
            <span className="block truncate font-mono text-[8px] font-normal opacity-60">{item.hint}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}

function SovereignRuntimeShell({ state, children }: { state: RuntimeFrameState; children: ReactNode }) {
  const [panelOpen, setPanelOpen] = useState(false);
  const active = currentModule(state);
  const activeColor = SIGNAL_COLOR[active.signal];

  return (
    <section
      className="mx-auto flex h-[100dvh] w-full max-w-[393px] flex-col overflow-hidden bg-black text-slate-100"
      data-testid="sovereign-app-wrapper"
      data-layout="composition-wrapper-around-existing-app"
    >
      <div className="flex h-6 flex-shrink-0 items-center justify-between bg-black px-3 font-mono text-[9px] text-slate-500">
        <span>Sovereign</span>
        <span style={{ color: activeColor }}>{active.signal}</span>
      </div>

      <div className="flex h-12 flex-shrink-0 items-center gap-2 border-b border-slate-800 bg-[#0d1117] px-3">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-lg border font-mono text-xs"
          style={{
            color: activeColor,
            borderColor: `${activeColor}66`,
            background: `${activeColor}14`,
          }}
        >
          {active.id.slice(0, 3).toUpperCase()}
        </div>

        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-bold text-slate-100">Sovereign Runtime Frame</p>
          <p className="truncate font-mono text-[9px] text-slate-500">
            {active.id} · {state.signalSummary}
          </p>
        </div>

        <span
          className="rounded border px-2 py-1 font-mono text-[9px]"
          style={{ color: activeColor, borderColor: `${activeColor}55` }}
        >
          OBS
        </span>

        <button
          type="button"
          className="h-8 w-8 rounded-md border border-slate-700 bg-slate-900 text-slate-400"
          onClick={() => setPanelOpen((value) => !value)}
          aria-label={panelOpen ? 'Runtime Panel schließen' : 'Runtime Panel öffnen'}
        >
          {panelOpen ? '▾' : '▴'}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto bg-black" data-testid="sovereign-wrapper-center">
        {children}
      </div>

      {panelOpen ? <RuntimePanel state={state} module={active} /> : null}
      <WorkspaceMenu />

      <nav className="grid h-14 flex-shrink-0 grid-cols-8 border-t border-slate-900 bg-black" aria-label="Sovereign runtime wrapper modules">
        {state.modules.map((module) => (
          <div
            key={module.id}
            className="min-w-0 border-t-2 px-1 py-1 text-center"
            style={{ borderColor: module.id === active.id ? SIGNAL_COLOR[module.signal] : 'transparent' }}
          >
            <span className="mx-auto mb-1 flex justify-center">
              <RuntimeLamp signal={module.signal} />
            </span>
            <span className="block truncate font-mono text-[7.5px] text-slate-500">
              {module.id.slice(0, 3).toUpperCase()}
            </span>
          </div>
        ))}
      </nav>

      <span className="sr-only">{state.sessionSummary}</span>
    </section>
  );
}

export default function SovereignAppWrapper() {
  const [published, setPublished] = useState<PublishedRuntimeSnapshot | null>(() => {
    if (typeof window === 'undefined') return null;
    return readPublishedRuntimeSnapshot((window as SovereignWindow).__sovereignSetupState);
  });

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const handlePublishedRuntime = (event: Event): void => {
      setPublished(readPublishedRuntimeSnapshot((event as CustomEvent<unknown>).detail));
    };

    window.addEventListener('sovereign:setup-state', handlePublishedRuntime);
    return () => window.removeEventListener('sovereign:setup-state', handlePublishedRuntime);
  }, []);

  const frameState = useMemo(() => deriveRuntimeFrameState(published), [published]);

  return (
    <SovereignRuntimeShell state={frameState}>
      <App />
    </SovereignRuntimeShell>
  );
}
