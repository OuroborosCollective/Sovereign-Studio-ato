import React, { ReactNode, useState } from 'react';
import type { SovereignControlFrameModuleId } from '../runtime/sovereignControlFrameContract';
import type { SovereignControlFrameState, SovereignControlModuleState } from '../runtime/sovereignControlFrameRuntime';

export interface SovereignControlFrameProps {
  readonly state: SovereignControlFrameState;
  readonly children: ReactNode;
  readonly title?: string;
  readonly onModuleSelect?: (moduleId: SovereignControlFrameModuleId) => void;
}

function currentModule(state: SovereignControlFrameState): SovereignControlModuleState {
  return state.modules.find((module) => module.id === state.activeModuleId) ?? state.modules[0];
}

function ControlLamp({ module }: { readonly module: SovereignControlModuleState }) {
  return <span className={`sovereign-control-frame__lamp sovereign-control-frame__lamp--${module.signal}`} aria-hidden="true" />;
}

function RuntimePanel({ state, module }: { readonly state: SovereignControlFrameState; readonly module: SovereignControlModuleState }) {
  return (
    <div className="sovereign-control-frame__runtime-panel" data-testid="control-frame-runtime-panel">
      <div className="sovereign-control-frame__runtime-grid">
        <div className="sovereign-control-frame__runtime-log" tabIndex={0}>
          {state.logs.length ? state.logs.map((line) => (
            <p key={`${line.moduleId}:${line.level}:${line.message}`}>
              <span className="sovereign-control-frame__runtime-key">[{line.moduleId}]</span>{' '}
              <span>{line.level.toUpperCase()}</span>{' '}
              <span>{line.message}</span>
            </p>
          )) : <p className="sovereign-control-frame__runtime-empty">no active runtime signals</p>}
        </div>
        <div className="sovereign-control-frame__conditions" tabIndex={0}>
          <p className="sovereign-control-frame__section-label">Condition chain</p>
          {module.conditions.map((condition) => (
            <p key={`${module.id}:${condition.label}`} className="sovereign-control-frame__condition">
              <span>{condition.label}</span>
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
  const runtimeBusy = state.modules.some((module) => module.signal === 'processing');

  return (
    <section
      className={`sovereign-control-frame sovereign-control-frame--${active.signal}`}
      data-testid="sovereign-control-frame"
      data-layout="control-frame-around-workspace-monitor"
      aria-busy={runtimeBusy}
    >
      <div className="sovereign-control-frame__statusbar" data-testid="control-frame-android-status-bar" aria-label="Runtime readback summary">
        <span className="sovereign-control-frame__status-label">Runtime readback</span>
        <span className="sovereign-control-frame__confidence">
          Confidence <strong className={`sovereign-control-frame__signal sovereign-control-frame__signal--${active.signal}`}>{state.confidence.toFixed(2)}</strong>
        </span>
      </div>

      <div className="sovereign-control-frame__toolbar" data-testid="control-frame-top-toolbar">
        <div className={`sovereign-control-frame__signal-mark sovereign-control-frame__signal-mark--${active.signal}`} aria-hidden="true">{active.id.slice(0, 3).toUpperCase()}</div>
        <div className="sovereign-control-frame__heading">
          <p className="sovereign-control-frame__title">{title}</p>
          <p className="sovereign-control-frame__summary" aria-live="polite">{active.id} · {state.signalSummary}</p>
        </div>
        <span className={`sovereign-control-frame__mode sovereign-control-frame__mode--${active.signal}`}>{state.overrideActive ? 'OVR' : 'AUTO'}</span>
        <button
          type="button"
          className="sovereign-control-frame__runtime-toggle"
          onClick={() => setPanelOpen((value) => !value)}
          aria-label={panelOpen ? 'Close runtime panel' : 'Open runtime panel'}
          title={panelOpen ? 'Close runtime panel' : 'Open runtime panel'}
          aria-expanded={panelOpen}
          aria-controls="control-frame-runtime-panel"
        >
          {panelOpen ? '▾' : '▴'}
        </button>
      </div>

      <div className="sovereign-control-frame__workspace" data-testid="control-frame-center-workspace-monitor">
        {children}
      </div>

      {panelOpen ? <div id="control-frame-runtime-panel"><RuntimePanel state={state} module={active} /></div> : null}

      <nav className="sovereign-control-frame__module-nav" data-testid="control-frame-bottom-nav" aria-label="Sovereign modules">
        {state.modules.map((module) => (
          <button
            key={module.id}
            type="button"
            className={`sovereign-control-frame__module-button sovereign-control-frame__module-button--${module.signal}`}
            aria-pressed={module.id === active.id}
            onClick={() => onModuleSelect?.(module.id)}
            aria-label={module.id.toUpperCase()}
            title={module.id.toUpperCase()}
          >
            <span className="sovereign-control-frame__lamp-wrap"><ControlLamp module={module} /></span>
            <span className="sovereign-control-frame__module-name">{module.id.slice(0, 3).toUpperCase()}</span>
          </button>
        ))}
      </nav>
    </section>
  );
}
