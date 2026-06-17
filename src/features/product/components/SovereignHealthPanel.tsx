import type { SovereignHealthReport } from '../runtime/sovereignHealth';

export interface SovereignHealthPanelProps {
  report: SovereignHealthReport;
}

function statusClass(status: string): string {
  if (status === 'green') return 'text-emerald-300';
  if (status === 'red') return 'text-red-300';
  if (status === 'warning') return 'text-amber-300';
  return 'text-slate-300';
}

export function SovereignHealthPanel({ report }: SovereignHealthPanelProps) {
  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Sovereign Health Dashboard</h2>
          <p className="mt-1 text-xs text-slate-400">{report.summary}</p>
        </div>
        <span className={`rounded bg-slate-900 px-2 py-1 text-xs font-bold uppercase ${statusClass(report.status)}`}>
          {report.status}
        </span>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <div className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center">
          <p className="text-xs text-slate-500">Critical Risks</p>
          <p className="text-2xl font-black">{report.criticalRisks}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center">
          <p className="text-xs text-slate-500">Total Issues</p>
          <p className="text-2xl font-black">{report.totalIssues}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center">
          <p className="text-xs text-slate-500">Repair Signals</p>
          <p className="text-2xl font-black">{report.repairsLogged}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center">
          <p className="text-xs text-slate-500">Branch Delta</p>
          <p className={`text-2xl font-black ${report.branchDelta > 0 ? 'text-red-300' : report.branchDelta < 0 ? 'text-emerald-300' : 'text-slate-300'}`}>
            {report.branchDelta > 0 ? '+' : ''}{report.branchDelta}
          </p>
        </div>
      </div>

      <div className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3">
        <h3 className="font-bold">Recommendations</h3>
        <ul className="mt-2 list-disc pl-5 text-xs text-slate-400">
          {report.recommendations.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    </section>
  );
}
