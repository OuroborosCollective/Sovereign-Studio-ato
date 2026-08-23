import { useState } from 'react';
import type { ChangelogGenerationResult } from '../runtime/changelogRuntime';

interface ChangelogPreviewCardProps {
  readonly result: ChangelogGenerationResult;
  readonly onClose: () => void;
  readonly onUseAsMission: (markdown: string) => void;
}

export function ChangelogPreviewCard({ result, onClose, onUseAsMission }: ChangelogPreviewCardProps) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard?.writeText(result.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section
      className="mx-3 my-2 rounded-xl border border-sky-500/30 bg-sky-500/10 p-3 text-sm"
      aria-labelledby="changelog-preview-title"
      data-testid="changelog-preview-card"
    >
      <div className="flex items-center justify-between gap-3">
        <strong id="changelog-preview-title">Keep-a-Changelog Vorschau</strong>
        <button
          type="button"
          className="rounded px-2 py-1 text-xs focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
          onClick={onClose}
          aria-label="Keep-a-Changelog Vorschau schließen"
          title="Keep-a-Changelog Vorschau schließen"
        >
          Schließen
        </button>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {result.commitCount} echte Commit(s) · {result.source}{result.error ? ` · Fallback: ${result.error}` : ''}
      </p>
      <pre
        tabIndex={0}
        aria-label="Changelog Markdown Vorschau"
        className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border bg-background/60 p-3 text-xs focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
      >
        {result.markdown}
      </pre>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md border px-3 py-2 text-xs transition-colors focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
          onClick={() => void copy()}
          aria-label={copied ? 'Markdown in Zwischenablage kopiert' : 'Vorschau-Markdown in die Zwischenablage kopieren'}
          title={copied ? 'In Zwischenablage kopiert!' : 'Vorschau-Markdown in die Zwischenablage kopieren'}
        >
          {copied ? 'Kopiert ✓' : 'Kopieren'}
        </button>
        <button
          type="button"
          className="rounded-md bg-primary px-3 py-2 text-xs text-primary-foreground focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none"
          onClick={() => onUseAsMission(result.markdown)}
          aria-label="Als CHANGELOG-Auftrag in den Builder übernehmen"
          title="Als CHANGELOG-Auftrag in den Builder übernehmen"
        >
          Als CHANGELOG-Auftrag übernehmen
        </button>
      </div>
    </section>
  );
}
