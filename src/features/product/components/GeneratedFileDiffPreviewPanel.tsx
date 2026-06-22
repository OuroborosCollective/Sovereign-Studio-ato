import type { GeneratedFileDiffReport } from '../runtime/generatedFileDiffPreview';

export interface GeneratedFileDiffPreviewPanelProps {
  report: GeneratedFileDiffReport | null;
  isLoading: boolean;
  onLoadSources: () => void;
}

function statusOf(report: GeneratedFileDiffReport | null, isLoading: boolean): string {
  if (isLoading) return 'loading-source-snapshots';
  if (!report) return 'waiting-for-package';
  if (report.sourceMissing > 0) return 'source-snapshots-missing';
  if (report.modified > 0 || report.created > 0) return 'changes-detected';
  return 'no-visible-changes';
}

/**
 * Diff review is now an internal runtime handoff, not a user-facing work stop.
 *
 * The old panel made the app look stuck on "Generated File Diff Preview" even when the
 * publishing/workflow logic had already moved on. Keep this component mounted for tests
 * and internal diagnostics, but remove it from the visual and pointer interaction path.
 */
export function GeneratedFileDiffPreviewPanel({ report, isLoading }: GeneratedFileDiffPreviewPanelProps) {
  return (
    <section
      aria-hidden="true"
      data-testid="generated-file-diff-preview__internal"
      data-diff-status={statusOf(report, isLoading)}
      data-generated-files={report?.files.length ?? 0}
      hidden
    />
  );
}
