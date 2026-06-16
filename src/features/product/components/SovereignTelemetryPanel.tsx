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

export function SovereignTelemetryPanel({ state, expanded, onToggle }: SovereignTelemetryPanelProps) {
  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/70 text-sm text-slate-200">
      <button
        className="flex w-full items-center justify-between p-3 text-left"
        onClick={onToggle}
        type="button"
      >
        <span>
          <span className="font-bold">Sovereign Telemetry Terminal</span>
          <span className="ml-2 text-xs text-slate-400">{summarizeTelemetry(state)}</span>
        </span>
        <span className="text-xs text-slate-400">{expanded ? 'collapse' : 'expand'}</span>
      </button>

      {expanded ? (
        <div className="border-t border-slate-800 p-3">
          {state.events.length === 0 ? (
            <p className="text-xs text-slate-500">No telemetry events yet.</p>
          ) : (
            <div className="max-h-80 overflow-auto rounded bg-black/40 p-3 font-mono text-[11px]">
              {state.events.slice().reverse().map((event) => (
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
}
