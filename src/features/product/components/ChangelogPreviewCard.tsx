import type { ChangelogGenerationResult } from '../runtime/changelogRuntime';

interface ChangelogPreviewCardProps {
  readonly result: ChangelogGenerationResult;
  readonly onClose: () => void;
  readonly onUseAsMission: (markdown: string) => void;
}

export function ChangelogPreviewCard({ result, onClose, onUseAsMission }: ChangelogPreviewCardProps) {
  const copy = async () => {
    await navigator.clipboard?.writeText(result.markdown);
  };
  return (
    <section className="mx-3 my-2 rounded-xl border border-sky-500/30 bg-sky-500/10 p-3 text-sm" data-testid="changelog-preview-card">
      <div className="flex items-center justify-between gap-3">
        <strong>Keep-a-Changelog Vorschau</strong>
        <button type="button" className="px-2 py-1 text-xs" onClick={onClose}>Schließen</button>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {result.commitCount} echte Commit(s) · {result.source}{result.error ? ` · Fallback: ${result.error}` : ''}
      </p>
      <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border bg-background/60 p-3 text-xs">{result.markdown}</pre>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="rounded-md border px-3 py-2 text-xs" onClick={() => void copy()}>Kopieren</button>
        <button type="button" className="rounded-md bg-primary px-3 py-2 text-xs text-primary-foreground" onClick={() => onUseAsMission(result.markdown)}>Als CHANGELOG-Auftrag übernehmen</button>
      </div>
    </section>
  );
}
