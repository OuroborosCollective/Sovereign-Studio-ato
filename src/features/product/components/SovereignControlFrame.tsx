import React, { ReactNode, useState } from 'react';
import type { SovereignControlFrameModuleId } from '../runtime/sovereignControlFrameContract';
import type { SovereignControlFrameState, SovereignControlModuleState } from '../runtime/sovereignControlFrameRuntime';

export interface SovereignControlFrameProps {
  readonly state: SovereignControlFrameState;
  readonly children: ReactNode;
  readonly title?: string;
  readonly onModuleSelect?: (moduleId: SovereignControlFrameModuleId) => void;
}

const SIGNAL_COLOR = {
  idle: '#30363d',
  active: '#3fb950',
  processing: '#58a6ff',
  warning: '#d29922',
  error: '#f85149',
} as const;

function currentModule(state: SovereignControlFrameState): SovereignControlModuleState {
  return state.modules.find((module) => module.id === state.activeModuleId) ?? state.modules[0];
}

function ControlLamp({ module }: { readonly module: SovereignControlModuleState }) {
  const color = SIGNAL_COLOR[module.signal];
  return (
    <span
      className="inline-block h-2.5 w-2.5 rounded-full"
      style={{
        background: module.signal === 'idle' ? '#21262d' : color,
        boxShadow: module.signal === 'idle' ? 'none' : `0 0 7px ${color}`,
      }}
    />
  );
}

function RuntimePanel({ state, module }: { readonly state: SovereignControlFrameState; readonly module: SovereignControlModuleState }) {
  return (
    <div className="border-t border-slate-800 bg-[#0d1117]" data-testid="control-frame-runtime-panel">
      <div className="grid h-28 grid-cols-1 gap-2 overflow-hidden p-2 sm:grid-cols-2">
        <div className="overflow-y-auto rounded-md border border-slate-800 bg-black/70 px-2 py-1 font-mono text-[10px] leading-5 text-slate-300">
          {state.logs.length ? state.logs.map((line) => (
            <p key={`${line.moduleId}:${line.level}:${line.message}`}>
              <span className="text-slate-600">[{line.moduleId}]</span> <span>{line.level.toUpperCase()}</span> <span>{line.message}</span>
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

export function SovereignControlFrame({ state, children, title = 'Sovereign Control', onModuleSelect }: SovereignControlFrameProps) {
  const [panelOpen, setPanelOpen] = useState(true);
  const active = currentModule(state);
  const color = SIGNAL_COLOR[active.signal];

  return (
    <section className="mx-auto flex h-[100dvh] w-full max-w-[393px] flex-col overflow-hidden bg-black text-slate-100" data-testid="sovereign-control-frame" data-layout="control-frame-around-chat-workbench">
      <div className="flex h-6 flex-shrink-0 items-center justify-between bg-black px-3 font-mono text-[9px] text-slate-500" data-testid="control-frame-android-status-bar">
        <span>{new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</span>
        <span>conf <span style={{ color }}>{state.confidence.toFixed(2)}</span></span>
      </div>

      <div className="flex h-12 flex-shrink-0 items-center gap-2 border-b border-slate-800 bg-[#0d1117] px-3" data-testid="control-frame-top-toolbar">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border font-mono text-xs" style={{ color, borderColor: `${color}66`, background: `${color}14` }}>{active.id.slice(0, 3).toUpperCase()}</div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-bold text-slate-100">{title}</p>
          <p className="truncate font-mono text-[9px] text-slate-500">{active.id} · {state.signalSummary}</p>
        </div>
        <span className="rounded border px-2 py-1 font-mono text-[9px]" style={{ color, borderColor: `${color}55` }}>{state.overrideActive ? 'OVR' : 'AUTO'}</span>
        <button type="button" className="h-8 w-8 rounded-md border border-slate-700 bg-slate-900 text-slate-400" onClick={() => setPanelOpen((value) => !value)}>{panelOpen ? '▾' : '▴'}</button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden bg-black" data-testid="control-frame-center-chat-workbench">
        {children}
      </div>

      {panelOpen ? <RuntimePanel state={state} module={active} /> : null}

      <nav className="grid h-14 flex-shrink-0 grid-cols-8 border-t border-slate-900 bg-black" data-testid="control-frame-bottom-nav">
        {state.modules.map((module) => (
          <button key={module.id} type="button" className="min-w-0 border-t-2 px-1 py-1 text-center" style={{ borderColor: module.id === active.id ? SIGNAL_COLOR[module.signal] : 'transparent' }} onClick={() => onModuleSelect?.(module.id)}>
            <span className="mx-auto mb-1 flex justify-center"><ControlLamp module={module} /></span>
            <span className="block truncate font-mono text-[7.5px] text-slate-500">{module.id.slice(0, 3).toUpperCase()}</span>
          </button>
        ))}
      </nav>
    </section>
  );
}
