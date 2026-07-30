import React from 'react';
import {
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
  Loader2,
  Play,
  Lock,
  ExternalLink,
} from 'lucide-react';
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

function getStatusIcon(status: string) {
  if (status === 'green') return <CheckCircle2 size={13} className="text-emerald-400 inline mr-1" aria-hidden="true" />;
  if (status === 'red') return <XCircle size={13} className="text-red-400 inline mr-1" aria-hidden="true" />;
  if (status === 'pending') return <Clock size={13} className="text-amber-400 inline mr-1" aria-hidden="true" />;
  return <AlertCircle size={13} className="text-slate-400 inline mr-1" aria-hidden="true" />;
}

export function WorkflowWatchPanel({
  report,
  isWatching,
  canWatch = true,
  statusMessage,
  onWatch,
}: WorkflowWatchPanelProps) {
  const helperText = statusMessage ?? (report ? report.summary : 'Create a Draft PR first, then watch the commit checks.');
  const waitingForDraft = !report && helperText.toLowerCase().includes('draft pr');
  const isBlocked = !canWatch || waitingForDraft;

  const buttonLabel = isBlocked
    ? 'Draft PR zuerst erstellen'
    : isWatching
      ? 'Watching...'
      : 'Watch Commit Checks';

  const buttonTitle = isBlocked
    ? 'Aktion blockiert: Draft-PR erforderlich'
    : isWatching
      ? 'Die Überwachung der Commit-Checks läuft aktuell'
      : 'Commit-Checks für diesen Draft-PR überwachen';

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200" aria-label="Workflow Watcher">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Workflow Watch</h2>
          <p className="mt-1 text-xs text-slate-400">
            {helperText}
          </p>
        </div>
        <button
          onClick={onWatch}
          disabled={isWatching || isBlocked}
          type="button"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 focus-visible:ring-2 focus-visible:ring-indigo-500 outline-none text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          title={buttonTitle}
        >
          {isBlocked && <Lock size={12} className="inline animate-none" aria-hidden="true" />}
          {!isBlocked && isWatching && <Loader2 size={12} className="inline animate-spin" aria-hidden="true" />}
          {!isBlocked && !isWatching && <Play size={12} className="inline animate-none" aria-hidden="true" />}
          {buttonLabel}
        </button>
      </div>

      {report ? (
        <div className="mt-4 grid gap-3">
          <div className="rounded border border-slate-800 bg-slate-900/70 p-3 flex items-center justify-between">
            <div>
              <p className={`font-bold uppercase flex items-center ${statusClass(report.status)}`}>
                {getStatusIcon(report.status)} Status: {report.status}
              </p>
              <p className="mt-1 text-xs text-slate-400">Commit: {report.commitSha ?? 'none'} • Branch: {report.branch ?? 'unknown'}</p>
            </div>
          </div>

          {report.checks.length ? (
            <div className="rounded border border-slate-800 overflow-hidden">
              <table className="w-full border-collapse text-left text-xs">
                <thead className="bg-slate-900 text-slate-400">
                  <tr>
                    <th scope="col" className="p-2">Check</th>
                    <th scope="col" className="p-2">Status</th>
                    <th scope="col" className="p-2">Source</th>
                    <th scope="col" className="p-2">Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {report.checks.map((check) => (
                    <tr key={`${check.source}:${check.name}:${check.url ?? ''}`} className="border-t border-slate-800 hover:bg-slate-900/30 transition-colors">
                      <td className="p-2 font-bold text-slate-100">
                        {check.url ? (
                          <a
                            href={check.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 hover:underline focus-visible:ring-2 focus-visible:ring-indigo-500 rounded outline-none"
                            aria-label={`GitHub Check Details für ${check.name} öffnen`}
                            title={`GitHub Check Details für ${check.name} in neuem Tab öffnen`}
                          >
                            {check.name}
                            <ExternalLink size={11} className="inline-block" aria-hidden="true" />
                          </a>
                        ) : (
                          check.name
                        )}
                      </td>
                      <td className={`p-2 font-bold uppercase ${statusClass(check.status)}`}>
                        <span className="flex items-center">
                          {getStatusIcon(check.status)}
                          {check.status}
                        </span>
                      </td>
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
