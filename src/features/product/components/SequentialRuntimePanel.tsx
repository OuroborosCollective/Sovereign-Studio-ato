import React from 'react';
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

function statusLabel(status: string): string {
  if (status === 'completed') return 'Completed';
  if (status === 'running') return 'Running';
  if (status === 'failed') return 'Failed';
  if (status === 'skipped') return 'Skipped';
  return 'Idle';
}

export function SequentialRuntimePanel({ state }: SequentialRuntimePanelProps) {
  const lockStatus = state.activeStep ? 'locked' : 'ready';
  const lockTitle = state.activeStep
    ? `Guard locked by active step: ${describeSequentialStep(state.activeStep)}`
    : 'Guard ready for next execution step';

  return (
    <section
      aria-labelledby="sequential-runtime-guard-heading"
      className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="sequential-runtime-guard-heading" className="font-bold">
            Sequential Runtime Guard
          </h2>
          <p className="mt-1 text-xs text-slate-400">{summarizeSequentialRuntime(state)}</p>
        </div>
        <span
          role="status"
          aria-label={`Runtime guard status: ${lockStatus}`}
          title={lockTitle}
          className={`font-mono text-xs font-bold uppercase ${
            state.activeStep ? 'text-sky-300' : 'text-emerald-300'
          }`}
        >
          {lockStatus}
        </span>
      </div>

      <ul
        role="list"
        aria-label="Sequential runtime steps"
        className="mt-4 grid gap-2 list-none p-0 m-0 md:grid-cols-3"
      >
        {SEQUENTIAL_RUNTIME_STEPS.map((step) => {
          const record = state.steps[step];
          const stepName = describeSequentialStep(step);
          const statusText = statusLabel(record.status);
          const stepTitle = `${stepName} – Status: ${statusText}${record.message ? ` (${record.message})` : ''}`;

          return (
            <li
              key={step}
              title={stepTitle}
              className="rounded border border-slate-800 bg-slate-900/70 p-3 transition-colors hover:border-slate-700 hover:bg-slate-900/90"
            >
              <p className="font-bold text-slate-100">{stepName}</p>
              <p
                role="status"
                aria-label={`${stepName} status: ${statusText}`}
                className={`mt-1 text-xs font-bold uppercase ${statusClass(record.status)}`}
              >
                {record.status}
              </p>
              {record.message ? (
                <p className="mt-1 text-[11px] text-slate-400" title={record.message}>
                  {record.message}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>

      {state.history.length ? (
        <details className="mt-4 group">
          <summary
            title="Toggle runtime transition history"
            className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400 transition-colors hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded px-1 -mx-1"
          >
            Runtime transition history ({state.history.length})
          </summary>
          <div
            tabIndex={0}
            role="region"
            aria-label="Runtime transition history table"
            className="mt-2 max-h-72 overflow-auto rounded border border-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            <table className="w-full border-collapse text-left text-xs">
              <thead className="bg-slate-900 text-slate-400 sticky top-0">
                <tr>
                  <th scope="col" className="p-2">#</th>
                  <th scope="col" className="p-2">Step</th>
                  <th scope="col" className="p-2">Status</th>
                  <th scope="col" className="p-2">Message</th>
                </tr>
              </thead>
              <tbody>
                {state.history.slice().reverse().map((event) => {
                  const eventStepName = describeSequentialStep(event.step);
                  const rowTitle = `Sequence #${event.sequence}: ${eventStepName} switched to ${event.status}${event.message ? ` - ${event.message}` : ''}`;
                  return (
                    <tr
                      key={event.sequence}
                      title={rowTitle}
                      className="border-t border-slate-800 transition-colors hover:bg-slate-900/50"
                    >
                      <td className="p-2 font-mono text-slate-500">{event.sequence}</td>
                      <td className="p-2 text-slate-300">{eventStepName}</td>
                      <td className={`p-2 font-bold uppercase ${statusClass(event.status)}`}>
                        {event.status}
                      </td>
                      <td className="p-2 text-slate-400">{event.message}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </section>
  );
}
