import { describe, expect, it } from 'vitest';
import { buildGeneratedFileDiffReportFromUnifiedDiff } from './generatedFileDiffPreview';

describe('buildGeneratedFileDiffReportFromUnifiedDiff', () => {
  it('derives file and line evidence from a real unified diff', () => {
    const report = buildGeneratedFileDiffReportFromUnifiedDiff([
      'diff --git a/src/auth.ts b/src/auth.ts',
      'index 111..222 100644',
      '--- a/src/auth.ts',
      '+++ b/src/auth.ts',
      '@@ -1 +1,2 @@',
      '-export const ok = false;',
      '+export const ok = true;',
      '+export const reason = "validated";',
    ].join('\n'));
    expect(report.files).toHaveLength(1);
    expect(report.files[0].path).toBe('src/auth.ts');
    expect(report.files[0].addedLines).toBe(2);
    expect(report.files[0].removedLines).toBe(1);
    expect(report.totalAddedLines).toBe(2);
  });
});
