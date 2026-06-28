import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import App from './App';
import {
  SOVEREIGN_WORKSPACE_COMMAND_EVENT,
  SOVEREIGN_WORKSPACE_MENU,
  createSovereignWorkspaceCommand,
  type SovereignWorkspaceTab,
} from './features/product/runtime/sovereignWorkspaceCommand';

type Signal = 'idle' | 'active' | 'processing' | 'warning' | 'error';

interface PublishedRuntimeSnapshot {
  repoReady: boolean;
  setupPhase: 'no-repo' | 'repo-loading' | 'repo-loaded' | 'repo-error';
  isBusy: boolean;
  status: string;
  dependencyHealthy: boolean;
  updatedAt: number;
}

interface MinimalLampState {
  signal: Signal;
  repoReady: boolean;
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

function deriveMinimalLampState(snapshot: PublishedRuntimeSnapshot | null): MinimalLampState {
  const signal: Signal = snapshot?.setupPhase === 'repo-error'
    ? 'error'
    : snapshot?.isBusy
      ? 'processing'
      : snapshot?.repoReady
        ? 'active'
        : snapshot
          ? 'warning'
          : 'idle';

  return {
    signal,
    repoReady: snapshot?.repoReady ?? false,
  };
}

function MinimalLampBar({ state }: { state: MinimalLampState }) {
  const color = SIGNAL_COLOR[state.signal];
  const statusText = state.signal === 'idle' ? '' : state.signal;

  return (
    <div
      className="flex h-7 flex-shrink-0 items-center justify-between border-b border-slate-800/50 bg-black/80 px-3 backdrop-blur-sm"
      data-testid="sovereign-minimal-lamp-bar"
      role="status"
      aria-label={`Runtime status: ${statusText || 'idle'}`}
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-2 w-2 rounded-full"
          style={{
            background: state.signal === 'idle' ? '#21262d' : color,
            boxShadow: state.signal === 'idle' ? 'none' : `0 0 6px ${color}`,
          }}
        />
        <span className="font-mono text-[9px] text-slate-500">
          {statusText || 'sovereign'}
        </span>
      </div>

      {state.repoReady && (
        <span className="font-mono text-[9px] text-slate-600">
          repo ready
        </span>
      )}
    </div>
  );
}

function publishWorkspaceCommand(targetTab: SovereignWorkspaceTab): void {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(new CustomEvent(SOVEREIGN_WORKSPACE_COMMAND_EVENT, {
    detail: createSovereignWorkspaceCommand(targetTab),
  }));
}

function WorkspaceMenu() {
  return (
    <nav
      className="sr-only"
      aria-label="Sovereign workspace bridge"
      data-testid="sovereign-wrapper-workspace-menu"
    >
      {SOVEREIGN_WORKSPACE_MENU.map((item) => (
        <button
          key={item.id}
          type="button"
          data-testid={`sovereign-wrapper-menu__${item.id}`}
          onClick={() => publishWorkspaceCommand(item.id)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}

function SovereignRuntimeShell({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<PublishedRuntimeSnapshot | null>(() => {
    if (typeof window === 'undefined') return null;
    return readPublishedRuntimeSnapshot((window as SovereignWindow).__sovereignSetupState);
  });

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const handlePublishedRuntime = (event: Event): void => {
      setSnapshot(readPublishedRuntimeSnapshot((event as CustomEvent<unknown>).detail));
    };

    window.addEventListener('sovereign:setup-state', handlePublishedRuntime);
    return () => window.removeEventListener('sovereign:setup-state', handlePublishedRuntime);
  }, []);

  const lampState = useMemo(() => deriveMinimalLampState(snapshot), [snapshot]);

  return (
    <div
      className="mx-auto flex h-[100dvh] w-full max-w-[393px] flex-col overflow-hidden bg-black text-slate-100"
      data-testid="sovereign-app-wrapper"
      data-layout="minimal-app-shell"
      data-contract="composition-wrapper-around-existing-app"
    >
      <MinimalLampBar state={lampState} />
      <WorkspaceMenu />

      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="sovereign-shell-content">
        {children}
      </div>
    </div>
  );
}

export default function SovereignAppWrapper() {
  return (
    <SovereignRuntimeShell>
      <App />
    </SovereignRuntimeShell>
  );
}
