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
  const branchDeltaText = report.branchDelta > 0 ? `+${report.branchDelta}` : `${report.branchDelta}`;

  return (
    <section
      aria-labelledby="sovereign-health-title"
      className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="sovereign-health-title" className="font-bold">Sovereign Health Dashboard</h2>
          <p className="mt-1 text-xs text-slate-400">{report.summary}</p>
        </div>
        <span
          role="status"
          aria-label={`Sovereign Health Status: ${report.status}`}
          title={`Sovereign Health Status: ${report.status}`}
          className={`rounded bg-slate-900 px-2 py-1 text-xs font-bold uppercase ${statusClass(report.status)}`}
        >
          {report.status}
        </span>
      </div>

      <ul
        aria-label="Health Metrics"
        className="mt-4 grid gap-3 md:grid-cols-4 list-none pl-0"
      >
        <li
          title={`Critical Risks: ${report.criticalRisks}`}
          className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center list-none"
        >
          <span className="block text-xs text-slate-500">Critical Risks</span>
          <span className="block text-2xl font-black">{report.criticalRisks}</span>
        </li>
        <li
          title={`Total Issues: ${report.totalIssues}`}
          className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center list-none"
        >
          <span className="block text-xs text-slate-500">Total Issues</span>
          <span className="block text-2xl font-black">{report.totalIssues}</span>
        </li>
        <li
          title={`Repair Signals: ${report.repairsLogged}`}
          className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center list-none"
        >
          <span className="block text-xs text-slate-500">Repair Signals</span>
          <span className="block text-2xl font-black">{report.repairsLogged}</span>
        </li>
        <li
          title={`Branch Delta: ${branchDeltaText}`}
          className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center list-none"
        >
          <span className="block text-xs text-slate-500">Branch Delta</span>
          <span className={`block text-2xl font-black ${report.branchDelta > 0 ? 'text-red-300' : report.branchDelta < 0 ? 'text-emerald-300' : 'text-slate-300'}`}>
            {report.branchDelta > 0 ? '+' : ''}{report.branchDelta}
          </span>
        </li>
      </ul>

      <div className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3">
        <h3 className="font-bold">Recommendations</h3>
        <ul className="mt-2 list-disc pl-5 text-xs text-slate-400">
          {report.recommendations.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    </section>
  );
}
