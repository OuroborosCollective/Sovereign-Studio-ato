import React, { memo, useMemo } from 'react';
import {
  SEQUENTIAL_RUNTIME_STEPS,
  describeSequentialStep,
  summarizeSequentialRuntime,
  type SequentialRuntimeState,
} from '../runtime/sequentialRuntimeGuard';

export interface SequentialRuntimePanelProps {
  state: SequentialRuntimeState;
}

function statusClass(status: string): string {
  if (status === 'completed') return 'text-emerald-300';
  if (status === 'running') return 'text-sky-300';
  if (status === 'failed') return 'text-red-300';
  if (status === 'skipped') return 'text-amber-300';
  return 'text-slate-500';
}

/**
 * ⚡ Bolt: SequentialRuntimePanel
 * Optimized with React.memo and useMemo to prevent redundant array operations
 * during frequent shell re-renders.
 */
export const SequentialRuntimePanel = memo(({ state }: SequentialRuntimePanelProps) => {
  const reversedHistory = useMemo(() =>
    state.history.slice().reverse(),
    [state.history]
  );

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Sequential Runtime Guard</h2>
          <p className="mt-1 text-xs text-slate-400">{summarizeSequentialRuntime(state)}</p>
        </div>
        <span className={state.activeStep ? 'text-sky-300' : 'text-emerald-300'}>
          {state.activeStep ? 'locked' : 'ready'}
        </span>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-3">
        {SEQUENTIAL_RUNTIME_STEPS.map((step) => {
          const record = state.steps[step];
          return (
            <div key={step} className="rounded border border-slate-800 bg-slate-900/70 p-3">
              <p className="font-bold text-slate-100">{describeSequentialStep(step)}</p>
              <p className={`mt-1 text-xs font-bold uppercase ${statusClass(record.status)}`}>{record.status}</p>
              {record.message ? <p className="mt-1 text-[11px] text-slate-500">{record.message}</p> : null}
            </div>
          );
        })}
      </div>

      {reversedHistory.length ? (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400">Runtime transition history</summary>
          <div className="mt-2 max-h-72 overflow-auto rounded border border-slate-800">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-2">#</th>
                  <th className="p-2">Step</th>
                  <th className="p-2">Status</th>
                  <th className="p-2">Message</th>
                </tr>
              </thead>
              <tbody>
                {reversedHistory.map((event) => (
                  <tr key={event.sequence} className="border-t border-slate-800">
                    <td className="p-2 text-slate-500">{event.sequence}</td>
                    <td className="p-2 text-slate-300">{describeSequentialStep(event.step)}</td>
                    <td className={`p-2 font-bold uppercase ${statusClass(event.status)}`}>{event.status}</td>
                    <td className="p-2 text-slate-400">{event.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </section>
  );
});

SequentialRuntimePanel.displayName = 'SequentialRuntimePanel';
