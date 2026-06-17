import type { RuntimeValidationCoverageReport } from '../runtime/runtimeValidationCoverage';

export interface RuntimeValidationCoveragePanelProps {
  report: RuntimeValidationCoverageReport;
}

function statusClass(status: string): string {
  if (status === 'covered') return 'text-emerald-300';
  if (status === 'partial') return 'text-amber-300';
  return 'text-red-300';
}

export function RuntimeValidationCoveragePanel({ report }: RuntimeValidationCoveragePanelProps) {
  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Runtime Validation Coverage</h2>
          <p className="mt-1 text-xs text-slate-400">{report.summary}</p>
        </div>
        <span className={report.healthy ? 'text-emerald-300' : 'text-red-300'}>{report.healthy ? 'healthy' : 'needs work'}</span>
      </div>

      <div className="mt-4 max-h-96 overflow-auto rounded border border-slate-800">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="sticky top-0 bg-slate-900 text-slate-400">
            <tr>
              <th className="p-2">Layer</th>
              <th className="p-2">Status</th>
              <th className="p-2">Runtime</th>
              <th className="p-2">Test</th>
              <th className="p-2">Integration</th>
            </tr>
          </thead>
          <tbody>
            {report.targets.map((target) => (
              <tr key={target.id} className="border-t border-slate-800">
                <td className="p-2">
                  <div className="font-bold text-slate-100">{target.id}</div>
                  <div className="text-[11px] text-slate-500">{target.purpose}</div>
                </td>
                <td className={`p-2 font-bold uppercase ${statusClass(target.status)}`}>{target.status}</td>
                <td className="p-2 font-mono text-[11px] text-slate-400">{target.runtimePath}</td>
                <td className="p-2 font-mono text-[11px] text-slate-400">{target.testPath}</td>
                <td className="p-2 text-slate-400">{target.integrationPoint}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
