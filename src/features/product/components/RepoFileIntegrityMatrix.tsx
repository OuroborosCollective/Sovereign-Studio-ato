import React, { memo, useMemo } from 'react';
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

/**
 * ⚡ Bolt & 🎨 Palette: RepoFileIntegrityMatrix
 * Optimized with React.memo and useMemo to prevent redundant O(N) file integrity analysis.
 * Enhanced with landmark linking, table header scope attributes, keyboard-navigable scroll region,
 * hover state feedback, and rich native tooltips for accessibility and micro-UX.
 */
export const RepoFileIntegrityMatrix = memo(({ files, limit = 80 }: RepoFileIntegrityMatrixProps) => {
  const results = useMemo(() =>
    analyzeRepoFileIntegrityList(files).slice(0, limit),
    [files, limit]
  );

  return (
    <section
      className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200"
      aria-labelledby="repo-file-integrity-title"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="repo-file-integrity-title" className="font-bold">
            Repo File Integrity Matrix
          </h2>
          <p className="text-xs text-slate-400">{summarizeFileIntegrity(results)}</p>
        </div>
        <span
          className="rounded bg-slate-900 px-2 py-1 text-[11px] text-slate-400"
          title="Static file-path heuristics analysis (content is not scanned)"
        >
          path-only, not content scan
        </span>
      </div>

      {results.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">Load a repository to inspect file risk markers.</p>
      ) : (
        <div
          tabIndex={0}
          role="region"
          aria-label="File integrity entries list"
          className="mt-3 max-h-96 overflow-auto rounded border border-slate-800 focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
        >
          <table className="w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 bg-slate-900 text-slate-400">
              <tr>
                <th scope="col" className="p-2">Risk</th>
                <th scope="col" className="p-2">Score</th>
                <th scope="col" className="p-2">File</th>
                <th scope="col" className="p-2">Flags</th>
                <th scope="col" className="p-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {results.map((file) => (
                <tr
                  key={file.path}
                  className="border-t border-slate-800 transition-colors hover:bg-slate-900/50"
                >
                  <td
                    className={`p-2 font-bold uppercase ${riskClass(file.riskLevel)}`}
                    title={`Risk: ${file.riskLevel} (Score: ${file.score})`}
                  >
                    {file.riskLevel}
                  </td>
                  <td className="p-2 font-mono" title={`Score: ${file.score}`}>
                    {file.score}
                  </td>
                  <td className="p-2" title={file.path}>
                    <div className="font-bold text-slate-100">{file.fileName}</div>
                    <div className="max-w-xl truncate text-[11px] text-slate-500">{file.path}</div>
                  </td>
                  <td
                    className="p-2 text-slate-300"
                    title={file.flags.length ? `Flags: ${file.flags.join(', ')}` : 'No risk flags'}
                  >
                    {file.flags.length ? file.flags.join(', ') : 'none'}
                  </td>
                  <td className="p-2 text-slate-400" title={file.reason}>
                    {file.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
});

RepoFileIntegrityMatrix.displayName = 'RepoFileIntegrityMatrix';
