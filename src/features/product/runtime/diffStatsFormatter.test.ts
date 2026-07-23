import { describe, expect, it } from 'vitest';
import { formatDiffStats, formatFileCount, formatLineCount } from './diffStatsFormatter';

describe('diffStatsFormatter', () => {
  it('formats singular file count', () => expect(formatFileCount(1)).toBe('1 Datei'));
  it('formats plural file count', () => expect(formatFileCount(3)).toBe('3 Dateien'));
  it('formats singular line count', () => expect(formatLineCount(1)).toBe('1 Zeile'));
  it('formats plural line count', () => expect(formatLineCount(4)).toBe('4 Zeilen'));
  it('formats line additions and removals', () => expect(formatDiffStats({ created: 1, modified: 2, unchanged: 0, sourceMissing: 0, totalAddedLines: 8, totalRemovedLines: 3 }).lineChangeSummary).toBe('+8 Zeilen / −3 Zeilen'));
  it('describes all file kinds', () => expect(formatDiffStats({ created: 1, modified: 2, unchanged: 3, sourceMissing: 4, totalAddedLines: 0, totalRemovedLines: 0 }).fileKindBreakdown).toBe('1 neu · 2 geändert · 3 unverändert · 4 ohne Snapshot'));
  it('reports no line changes honestly', () => { const result = formatDiffStats({ created: 0, modified: 0, unchanged: 2, sourceMissing: 0, totalAddedLines: 0, totalRemovedLines: 0 }); expect(result.hasChanges).toBe(false); expect(result.lineChangeSummary).toBe('Keine Zeilenänderungen'); });
  it('counts every file bucket', () => expect(formatDiffStats({ created: 1, modified: 2, unchanged: 3, sourceMissing: 4, totalAddedLines: 1, totalRemovedLines: 1 }).fileCountLabel).toBe('10 Dateien'));
});
