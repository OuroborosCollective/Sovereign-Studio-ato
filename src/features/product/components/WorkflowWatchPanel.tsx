import type { WorkflowWatchReport } from '../runtime/workflowWatch';

export interface WorkflowWatchPanelProps {
  report: WorkflowWatchReport | null;
  isWatching: boolean;
  canWatch?: boolean;
  statusMessage?: string;
  onWatch: () => void;
}

function statusClass(status: string): string {
  if (status === 'green') return 'text-emerald-300';
  if (status === 'red') return 'text-red-300';
  if (status === 'pending') return 'text-amber-300';
  return 'text-slate-300';
}

export function WorkflowWatchPanel({
  report,
  isWatching,
  canWatch = true,
  statusMessage,
  onWatch,
}: WorkflowWatchPanelProps) {
  const isBlocked = !canWatch;
  const helperText = statusMessage ?? (report ? report.summary : 'Create a Draft PR first, then watch the commit checks.');
  const buttonLabel = isWatching
    ? 'Watching...'
    : isBlocked
      ? 'Draft PR zuerst erstellen'
      : 'Watch Commit Checks';

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Workflow Watch</h2>
          <p className="mt-1 text-xs text-slate-400">
            {helperText}
          </p>
        </div>
        <button onClick={onWatch} disabled={isWatching || isBlocked} type="button">
          {buttonLabel}
        </button>
      </div>

      {report ? (
        <div className="mt-4 grid gap-3">
          <div className="rounded border border-slate-800 bg-slate-900/70 p-3">
            <p className={`font-bold uppercase ${statusClass(report.status)}`}>Status: {report.status}</p>
            <p className="mt-1 text-xs text-slate-400">Commit: {report.commitSha ?? 'none'} • Branch: {report.branch ?? 'unknown'}</p>
          </div>

          {report.checks.length ? (
            <div className="rounded border border-slate-800">
              <table className="w-full border-collapse text-left text-xs">
                <thead className="bg-slate-900 text-slate-400">
                  <tr>
                    <th className="p-2">Check</th>
                    <th className="p-2">Status</th>
                    <th className="p-2">Source</th>
                    <th className="p-2">Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {report.checks.map((check) => (
                    <tr key={`${check.source}:${check.name}:${check.url ?? ''}`} className="border-t border-slate-800">
                      <td className="p-2 font-bold text-slate-100">{check.name}</td>
                      <td className={`p-2 font-bold uppercase ${statusClass(check.status)}`}>{check.status}</td>
                      <td className="p-2 text-slate-400">{check.source}</td>
                      <td className="p-2 text-slate-400">{check.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="rounded border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-500">No checks found yet.</p>
          )}

          {report.fixes.length ? (
            <div className="rounded border border-slate-800 bg-slate-900/70 p-3">
              <h3 className="font-bold">Next repair ideas</h3>
              <ul className="mt-2 list-disc pl-5 text-xs text-slate-400">
                {report.fixes.map((fix) => <li key={fix}>{fix}</li>)}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
