import type { RepoFile } from '../../github/types';
import {
  DEFAULT_TOOL_PROGRESS_RAIL,
  buildLaunchPackageMarkdown,
  evaluateRepoReadiness,
} from '../runtime/repoLaunchReadiness';
import { buildRepoSignalsFromFiles } from '../runtime/repoLaunchReadinessFromFiles';

export interface RepoReadinessPanelProps {
  repoUrl: string;
  files: RepoFile[];
  status?: string;
}

function gradeClass(grade: string): string {
  if (grade === 'EXCELLENT') return 'text-emerald-400';
  if (grade === 'HEALTHY') return 'text-sky-400';
  if (grade === 'BLOCKED') return 'text-red-400';
  return 'text-amber-400';
}

export function RepoReadinessPanel({ repoUrl, files, status }: RepoReadinessPanelProps) {
  const signals = buildRepoSignalsFromFiles(repoUrl, files);
  const report = evaluateRepoReadiness(signals);
  const launchMarkdown = buildLaunchPackageMarkdown(signals, report, status ?? 'Loaded repository snapshot');

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-bold">Repo Launch Readiness</h2>
          <p className="text-xs text-slate-400">{report.summary}</p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-black">{report.score}/100</div>
          <div className={`text-xs font-bold ${gradeClass(report.grade)}`}>{report.grade}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-3">
        {DEFAULT_TOOL_PROGRESS_RAIL.map((stage) => (
          <div key={stage.id} className="rounded border border-slate-800 bg-slate-900/70 p-2">
            <div className="text-[11px] font-bold uppercase tracking-wide text-violet-300">{stage.label}</div>
            <div className="mt-1 text-[11px] text-slate-400">{stage.description}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">Risk Register</div>
          {report.risks.length === 0 ? (
            <p className="text-xs text-emerald-300">No blocking readiness risks detected.</p>
          ) : (
            <ul className="space-y-2">
              {report.risks.map((risk) => (
                <li key={risk.id} className="rounded bg-slate-900 p-2 text-xs">
                  <span className="font-bold uppercase text-amber-300">{risk.severity}</span> {risk.title}
                  <div className="mt-1 text-slate-400">{risk.mitigation}</div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">Owner Checklist</div>
          <ul className="space-y-2">
            {report.checklist.map((item) => (
              <li key={item.id} className="rounded bg-slate-900 p-2 text-xs">
                <span className={item.done ? 'text-emerald-300' : 'text-slate-500'}>{item.done ? '✓' : '□'}</span>{' '}
                <span className="font-bold">{item.owner}</span>: {item.text}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide text-slate-400">Launch package markdown</summary>
        <pre className="mt-2 max-h-72 overflow-auto rounded bg-black/40 p-3 text-[11px] text-slate-300">{launchMarkdown}</pre>
      </details>
    </section>
  );
}
