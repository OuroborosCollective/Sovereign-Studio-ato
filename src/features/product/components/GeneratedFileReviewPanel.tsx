import { reviewGeneratedFiles } from '../runtime/generatedFileReview';
import type { SovereignImplementationPackage } from '../runtime/sovereignRuntime';

export interface GeneratedFileReviewPanelProps {
  pkg: SovereignImplementationPackage | null;
}

function riskClass(risk: string): string {
  if (risk === 'high') return 'text-red-300';
  if (risk === 'medium') return 'text-amber-300';
  return 'text-emerald-300';
}

export function GeneratedFileReviewPanel({ pkg }: GeneratedFileReviewPanelProps) {
  if (!pkg) {
    return (
      <section
        className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200"
        aria-labelledby="generated-file-review-heading"
      >
        <h2 id="generated-file-review-heading" className="font-bold">
          Generated Files Review
        </h2>
        <p className="mt-2 text-xs text-slate-500">Build a Sovereign package first to review generated files before creating a Draft PR.</p>
      </section>
    );
  }

  const report = reviewGeneratedFiles(pkg.files);
  const selfReviewClass = report.selfReview.accepted
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
    : 'border-amber-500/30 bg-amber-500/10 text-amber-100';

  return (
    <section
      className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200"
      aria-labelledby="generated-file-review-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="generated-file-review-heading" className="font-bold">
            Generated Files Review
          </h2>
          <p className="text-xs text-slate-400">{report.summary}</p>
        </div>
        <span
          role="status"
          aria-label="Pre-publish review status: active"
          title="Pre-publish review status: active"
          className="rounded bg-slate-900 px-2 py-1 text-[11px] text-slate-400"
        >
          pre-publish review
        </span>
      </div>

      <div className={`mt-4 rounded-xl border p-3 text-xs ${selfReviewClass}`} data-testid="generated-self-review">
        <div className="font-black uppercase tracking-wide">{report.selfReview.accepted ? 'Self Review: accepted' : 'Self Review: rewrite required'}</div>
        <p className="mt-2">{report.selfReview.reason}</p>
        <p className="mt-1 text-[11px] opacity-80">Learning signal: {report.selfReview.learningSignal}</p>
        {report.selfReview.rewritePlan.length ? (
          <ol className="mt-2 list-decimal space-y-1 pl-4" aria-label="Self review rewrite plan">
            {report.selfReview.rewritePlan.map((step) => <li key={step}>{step}</li>)}
          </ol>
        ) : null}
      </div>

      <ul className="mt-4 grid gap-3 list-none p-0" role="list" aria-label="Generated file reviews">
        {report.files.map((file) => (
          <li key={file.path}>
            <details className="rounded border border-slate-800 bg-slate-900/70 p-3">
              <summary
                className="cursor-pointer focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none rounded transition-colors"
                title={`Toggle review details for ${file.path}`}
              >
                <span className={`mr-2 font-bold uppercase ${riskClass(file.risk)}`}>{file.risk}</span>
                <span className="font-mono text-xs text-slate-100">{file.path}</span>
                <span className="ml-2 text-[11px] text-slate-500">{file.lineCount} lines / {file.charCount} chars</span>
              </summary>
              <p className="mt-2 text-xs text-slate-400">{file.reason}</p>
              <p className="mt-1 text-[11px] text-slate-500">Flags: {file.flags.length ? file.flags.join(', ') : 'none'}</p>
              <pre
                tabIndex={0}
                aria-label={`Preview of ${file.path}`}
                className="mt-3 max-h-80 overflow-auto rounded bg-black/40 p-3 text-[11px] text-slate-300 focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
              >
                {file.preview}
              </pre>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}
