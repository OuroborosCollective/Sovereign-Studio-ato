import React, { memo, useMemo } from 'react';
import { formatTelemetryLine, summarizeTelemetry, type SovereignTelemetryState } from '../runtime/sovereignTelemetry';

export interface SovereignTelemetryPanelProps {
  state: SovereignTelemetryState;
  expanded: boolean;
  onToggle: () => void;
}

function levelClass(level: string): string {
  if (level === 'success') return 'text-emerald-300';
  if (level === 'warning') return 'text-amber-300';
  if (level === 'error') return 'text-red-300';
  return 'text-sky-300';
}

/**
 * ⚡ Bolt: SovereignTelemetryPanel
 * Optimized with React.memo and useMemo to prevent redundant O(N) array operations
 * (slicing and reversing) during frequent shell re-renders.
 */
export const SovereignTelemetryPanel = memo(({ state, expanded, onToggle }: SovereignTelemetryPanelProps) => {
  const latest = useMemo(() => state.events[state.events.length - 1] ?? null, [state.events]);

  const reversedEvents = useMemo(() =>
    state.events.slice().reverse(),
    [state.events]
  );

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/70 text-sm text-slate-200">
      <button
        className="flex w-full items-center justify-between p-3 text-left"
        onClick={onToggle}
        type="button"
      >
        <span>
          <span className="font-bold">NoCode Live Monitor · Telemetry Log</span>
          <span className="ml-2 text-xs text-slate-400">{summarizeTelemetry(state)}</span>
        </span>
        <span className="text-xs text-slate-400">{expanded ? 'collapse' : 'expand'}</span>
      </button>

      <div className="border-t border-slate-800 p-3">
        <div className="grid gap-2 text-xs md:grid-cols-4">
          <div className="rounded bg-slate-900/70 p-2">Events: {state.events.length}</div>
          <div className="rounded bg-slate-900/70 p-2">Repo: {state.latestByStage.repo?.level ?? 'idle'}</div>
          <div className="rounded bg-slate-900/70 p-2">Workflow: {state.latestByStage.workflow?.level ?? 'idle'}</div>
          <div className="rounded bg-slate-900/70 p-2">Memory: {state.latestByStage.memory?.level ?? 'idle'}</div>
        </div>
        {latest ? (
          <p className="mt-3 rounded bg-slate-900/70 p-2 text-xs text-slate-300">Latest: {formatTelemetryLine(latest)}</p>
        ) : (
          <p className="mt-3 rounded bg-slate-900/70 p-2 text-xs text-slate-500">Noch keine Live-Events. Lade ein Repo oder nutze Remote/Workflow-Aktionen.</p>
        )}
      </div>

      {expanded ? (
        <div className="border-t border-slate-800 p-3">
          {reversedEvents.length === 0 ? (
            <p className="text-xs text-slate-500">No telemetry events yet.</p>
          ) : (
            <div className="max-h-80 overflow-auto rounded bg-black/40 p-3 font-mono text-[11px]">
              {reversedEvents.map((event) => (
                <div key={event.id} className={levelClass(event.level)}>
                  {formatTelemetryLine(event)}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
});

SovereignTelemetryPanel.displayName = 'SovereignTelemetryPanel';
