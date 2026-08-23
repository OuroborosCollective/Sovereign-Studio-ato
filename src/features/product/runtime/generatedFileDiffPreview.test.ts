import { describe, expect, it } from 'vitest';
import {
  assertDiffPreviewReady,
  buildGeneratedFileDiffItem,
  buildGeneratedFileDiffReport,
  buildGeneratedFileDiffReportFromUnifiedDiff,
} from './generatedFileDiffPreview';

describe('generatedFileDiffPreview', () => {
  it('marks missing source as created when source says not found', () => {
    const item = buildGeneratedFileDiffItem(
      { path: 'docs/NEW.md', content: '# New', reason: 'docs' },
      { path: 'docs/NEW.md', content: null, found: false },
    );

    expect(item.kind).toBe('created');
    expect(item.preview).toContain('+++ docs/NEW.md');
  });

  it('marks existing changed files as modified', () => {
    const item = buildGeneratedFileDiffItem(
      { path: 'README.md', content: '# New\nBody', reason: 'docs' },
      { path: 'README.md', content: '# Old\nBody', found: true },
    );

    expect(item.kind).toBe('modified');
    expect(item.changed).toBe(true);
    expect(item.preview).toContain('-# Old');
    expect(item.preview).toContain('+# New');
  });

  it('builds report counts and readiness guard', () => {
    const report = buildGeneratedFileDiffReport(
      [
        { path: 'README.md', content: '# New', reason: 'docs' },
        { path: 'docs/NEW.md', content: '# New', reason: 'docs' },
      ],
      [
        { path: 'README.md', content: '# Old', found: true },
        { path: 'docs/NEW.md', content: null, found: false },
      ],
    );

    expect(report.modified).toBe(1);
    expect(report.created).toBe(1);
    expect(() => assertDiffPreviewReady(report)).not.toThrow();
  });

  it('blocks when no source snapshots were loaded', () => {
    const report = buildGeneratedFileDiffReport(
      [{ path: 'README.md', content: '# New', reason: 'docs' }],
      [],
    );
    expect(report.sourceMissing).toBe(1);
    expect(() => assertDiffPreviewReady(report)).toThrow('No source snapshots');
  });

  it('builds report correctly from unified diff string', () => {
    const unifiedDiff = `
diff --git a/src/app.ts b/src/app.ts
--- a/src/app.ts
+++ b/src/app.ts
@@ -1,3 +1,4 @@
 line 1
-line 2
+line 2 updated
+line 3 added
diff --git a/src/new.ts b/src/new.ts
new file mode 100644
--- /dev/null
+++ b/src/new.ts
@@ -0,0 +1,2 @@
+new line 1
+new line 2
`.trim();

    const report = buildGeneratedFileDiffReportFromUnifiedDiff(unifiedDiff);
    expect(report.files.length).toBe(2);
    expect(report.modified).toBe(1);
    expect(report.created).toBe(1);
    expect(report.totalAddedLines).toBe(4);
    expect(report.totalRemovedLines).toBe(1);
  });
});
