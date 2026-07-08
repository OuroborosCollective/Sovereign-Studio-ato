import type { ImplementationFile } from './sovereignRuntime';

export type GeneratedFileDiffKind = 'created' | 'modified' | 'unchanged' | 'source-missing';

export interface SourceFileSnapshot {
  path: string;
  content: string | null;
  found: boolean;
}

export interface GeneratedFileDiffItem {
  path: string;
  kind: GeneratedFileDiffKind;
  oldLineCount: number;
  newLineCount: number;
  addedLines: number;
  removedLines: number;
  changed: boolean;
  summary: string;
  preview: string;
}

export interface GeneratedFileDiffReport {
  files: GeneratedFileDiffItem[];
  created: number;
  modified: number;
  unchanged: number;
  sourceMissing: number;
  totalAddedLines: number;
  totalRemovedLines: number;
  summary: string;
}

function countLines(content: string | null | undefined): number {
  if (!content) return 0;
  return content.split(/\r?\n/).length;
}

function normalizeContent(content: string): string {
  return content.replace(/\r\n/g, '\n').replace(/\s+$/g, '');
}

function preview(content: string, maxChars = 1800): string {
  return content.length > maxChars ? `${content.slice(0, maxChars)}\n…` : content;
}

export function buildUnifiedLikePreview(path: string, oldContent: string | null, newContent: string): string {
  if (oldContent === null) {
    return [`+++ ${path}`, ...newContent.split(/\r?\n/).slice(0, 80).map((line) => `+${line}`)].join('\n');
  }

  const oldLines = oldContent.split(/\r?\n/);
  const newLines = newContent.split(/\r?\n/);
  const max = Math.max(oldLines.length, newLines.length);
  const out: string[] = [`--- ${path}`, `+++ ${path}`];
  let shown = 0;

  for (let i = 0; i < max && shown < 120; i += 1) {
    const oldLine = oldLines[i];
    const newLine = newLines[i];
    if (oldLine === newLine) continue;
    if (oldLine !== undefined) {
      out.push(`-${oldLine}`);
      shown += 1;
    }
    if (newLine !== undefined) {
      out.push(`+${newLine}`);
      shown += 1;
    }
  }

  return out.length === 2 ? `${out.join('\n')}\n(no line-level changes)` : out.join('\n');
}

export function buildGeneratedFileDiffItem(
  file: ImplementationFile,
  source?: SourceFileSnapshot,
): GeneratedFileDiffItem {
  const sourceFound = Boolean(source?.found);
  const oldContent = sourceFound ? source?.content ?? '' : null;
  const oldNormalized = oldContent === null ? null : normalizeContent(oldContent);
  const newNormalized = normalizeContent(file.content);
  const oldLineCount = countLines(oldContent);
  const newLineCount = countLines(file.content);
  const changed = oldNormalized !== newNormalized;

  const kind: GeneratedFileDiffKind = !source
    ? 'source-missing'
    : !sourceFound
      ? 'created'
      : changed
        ? 'modified'
        : 'unchanged';

  const addedLines = Math.max(0, newLineCount - oldLineCount);
  const removedLines = Math.max(0, oldLineCount - newLineCount);
  const summary = kind === 'created'
    ? `${file.path} will be created with ${newLineCount} line(s).`
    : kind === 'modified'
      ? `${file.path} will change from ${oldLineCount} to ${newLineCount} line(s).`
      : kind === 'unchanged'
        ? `${file.path} appears unchanged.`
        : `${file.path} has no source snapshot loaded yet.`;

  return {
    path: file.path,
    kind,
    oldLineCount,
    newLineCount,
    addedLines,
    removedLines,
    changed,
    summary,
    preview: preview(buildUnifiedLikePreview(file.path, oldContent, file.content)),
  };
}

export function buildGeneratedFileDiffReport(
  files: ImplementationFile[],
  sources: SourceFileSnapshot[],
): GeneratedFileDiffReport {
  const sourceByPath = new Map(sources.map((source) => [source.path, source]));
  const items = files.map((file) => buildGeneratedFileDiffItem(file, sourceByPath.get(file.path)));
  const created = items.filter((item) => item.kind === 'created').length;
  const modified = items.filter((item) => item.kind === 'modified').length;
  const unchanged = items.filter((item) => item.kind === 'unchanged').length;
  const sourceMissing = items.filter((item) => item.kind === 'source-missing').length;
  const totalAddedLines = items.reduce((sum, item) => sum + item.addedLines, 0);
  const totalRemovedLines = items.reduce((sum, item) => sum + item.removedLines, 0);

  return {
    files: items,
    created,
    modified,
    unchanged,
    sourceMissing,
    totalAddedLines,
    totalRemovedLines,
    summary: `${items.length} generated file(s): ${created} created, ${modified} modified, ${unchanged} unchanged, ${sourceMissing} without source snapshot.`,
  };
}

export function assertDiffPreviewReady(report: GeneratedFileDiffReport): void {
  if (!report.files.length) throw new Error('No generated files available for diff preview.');
  if (report.sourceMissing === report.files.length) {
    throw new Error('No source snapshots were loaded for generated file diff preview.');
  }
}
