import type { GeneratedFileDiffReport } from '../runtime/generatedFileDiffPreview';

export interface GeneratedFileDiffPreviewPanelProps {
  report: GeneratedFileDiffReport | null;
  isLoading: boolean;
  onLoadSources: () => void;
}

function kindClass(kind: string): string {
  if (kind === 'created') return 'text-emerald-300';
  if (kind === 'modified') return 'text-amber-300';
  if (kind === 'unchanged') return 'text-slate-300';
  return 'text-red-300';
}

export function GeneratedFileDiffPreviewPanel({ report, isLoading, onLoadSources }: GeneratedFileDiffPreviewPanelProps) {
  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Generated File Diff Preview</h2>
          <p className="mt-1 text-xs text-slate-400">
            {report ? report.summary : 'Build a package, then load source snapshots for generated files.'}
          </p>
        </div>
        <button onClick={onLoadSources} disabled={isLoading} type="button">
          {isLoading ? 'Loading sources...' : 'Load Source Snapshots'}
        </button>
      </div>

      {report ? (
        <div className="mt-4 grid gap-3">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center">
              <p className="text-xs text-slate-500">Created</p>
              <p className="text-2xl font-black">{report.created}</p>
            </div>
            <div className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center">
              <p className="text-xs text-slate-500">Modified</p>
              <p className="text-2xl font-black">{report.modified}</p>
            </div>
            <div className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center">
              <p className="text-xs text-slate-500">Added Lines</p>
              <p className="text-2xl font-black">+{report.totalAddedLines}</p>
            </div>
            <div className="rounded border border-slate-800 bg-slate-900/70 p-3 text-center">
              <p className="text-xs text-slate-500">Removed Lines</p>
              <p className="text-2xl font-black">-{report.totalRemovedLines}</p>
            </div>
          </div>

          {report.files.map((file) => (
            <details key={file.path} className="rounded border border-slate-800 bg-slate-900/70 p-3">
              <summary className="cursor-pointer">
                <span className={`mr-2 font-bold uppercase ${kindClass(file.kind)}`}>{file.kind}</span>
                <span className="font-mono text-xs text-slate-100">{file.path}</span>
                <span className="ml-2 text-[11px] text-slate-500">{file.oldLineCount} → {file.newLineCount} lines</span>
              </summary>
              <p className="mt-2 text-xs text-slate-400">{file.summary}</p>
              <pre className="mt-3 max-h-96 overflow-auto rounded bg-black/40 p-3 text-[11px] text-slate-300">{file.preview}</pre>
            </details>
          ))}
        </div>
      ) : null}
    </section>
  );
}
