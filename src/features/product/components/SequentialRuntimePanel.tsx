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

export function SequentialRuntimePanel({ state }: SequentialRuntimePanelProps) {
  const isLocked = Boolean(state.activeStep);
  const statusLabel = isLocked
    ? `Sequential Runtime Guard status: locked (${state.activeStep})`
    : 'Sequential Runtime Guard status: ready';

  return (
    <section
      aria-labelledby="sequential-runtime-guard-title"
      className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="sequential-runtime-guard-title" className="font-bold">
            Sequential Runtime Guard
          </h2>
          <p className="mt-1 text-xs text-slate-400">{summarizeSequentialRuntime(state)}</p>
        </div>
        <span
          role="status"
          aria-label={statusLabel}
          title={statusLabel}
          className={`text-xs font-bold uppercase tracking-wide ${isLocked ? 'text-sky-300' : 'text-emerald-300'}`}
        >
          {isLocked ? 'locked' : 'ready'}
        </span>
      </div>

      <ul role="list" aria-label="Sequential Runtime Steps" className="mt-4 grid gap-2 md:grid-cols-3">
        {SEQUENTIAL_RUNTIME_STEPS.map((step) => {
          const record = state.steps[step];
          const stepTitle = `${describeSequentialStep(step)}: ${record.status}${
            record.message ? ` – ${record.message}` : ''
          }`;

          return (
            <li
              key={step}
              title={stepTitle}
              className="rounded border border-slate-800 bg-slate-900/70 p-3"
            >
              <p className="font-bold text-slate-100">{describeSequentialStep(step)}</p>
              <p className={`mt-1 text-xs font-bold uppercase ${statusClass(record.status)}`}>
                {record.status}
              </p>
              {record.message ? <p className="mt-1 text-[11px] text-slate-500">{record.message}</p> : null}
            </li>
          );
        })}
      </ul>

      {state.history.length ? (
        <details className="mt-4 group">
          <summary
            title="Toggle runtime transition history"
            className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded px-1 transition-colors"
          >
            Runtime transition history
          </summary>
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
                {state.history
                  .slice()
                  .reverse()
                  .map((event) => (
                    <tr key={event.sequence} className="border-t border-slate-800">
                      <td className="p-2 text-slate-500">{event.sequence}</td>
                      <td className="p-2 text-slate-300">{describeSequentialStep(event.step)}</td>
                      <td
                        title={`Status: ${event.status}`}
                        className={`p-2 font-bold uppercase ${statusClass(event.status)}`}
                      >
                        {event.status}
                      </td>
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
}
