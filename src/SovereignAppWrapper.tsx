import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import App from './App';

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

function SovereignAppShell({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<PublishedRuntimeSnapshot | null>(() => {
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
    <div
      className="mx-auto flex h-[100dvh] w-full max-w-[393px] flex-col overflow-hidden bg-black text-slate-100"
      data-testid="sovereign-app-wrapper"
      data-layout="minimal-app-shell"
      data-contract="chat-first-sovereign-shell"
    >
      <MinimalLampBar state={lampState} />

      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="sovereign-shell-content">
        {children}
      </div>
    </div>
  );
}

export default function SovereignAppWrapper() {
  return (
    <SovereignAppShell>
      <App />
    </SovereignAppShell>
  );
}
