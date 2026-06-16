import type { RepoFile } from '../../github/types';
import { analyzeRepoFileIntegrityList, summarizeFileIntegrity } from '../runtime/repoFileIntegrity';

export interface RepoFileIntegrityMatrixProps {
  files: RepoFile[];
  limit?: number;
}

function riskClass(risk: string): string {
  if (risk === 'high') return 'text-red-300';
  if (risk === 'medium') return 'text-amber-300';
  return 'text-emerald-300';
}

export function RepoFileIntegrityMatrix({ files, limit = 80 }: RepoFileIntegrityMatrixProps) {
  const results = analyzeRepoFileIntegrityList(files).slice(0, limit);

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-bold">Repo File Integrity Matrix</h2>
          <p className="text-xs text-slate-400">{summarizeFileIntegrity(results)}</p>
        </div>
        <span className="rounded bg-slate-900 px-2 py-1 text-[11px] text-slate-400">path-only, not content scan</span>
      </div>

      {results.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">Load a repository to inspect file risk markers.</p>
      ) : (
        <div className="mt-3 max-h-96 overflow-auto rounded border border-slate-800">
          <table className="w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 bg-slate-900 text-slate-400">
              <tr>
                <th className="p-2">Risk</th>
                <th className="p-2">Score</th>
                <th className="p-2">File</th>
                <th className="p-2">Flags</th>
                <th className="p-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {results.map((file) => (
                <tr key={file.path} className="border-t border-slate-800">
                  <td className={`p-2 font-bold uppercase ${riskClass(file.riskLevel)}`}>{file.riskLevel}</td>
                  <td className="p-2 font-mono">{file.score}</td>
                  <td className="p-2">
                    <div className="font-bold text-slate-100">{file.fileName}</div>
                    <div className="max-w-xl truncate text-[11px] text-slate-500">{file.path}</div>
                  </td>
                  <td className="p-2 text-slate-300">{file.flags.length ? file.flags.join(', ') : 'none'}</td>
                  <td className="p-2 text-slate-400">{file.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
