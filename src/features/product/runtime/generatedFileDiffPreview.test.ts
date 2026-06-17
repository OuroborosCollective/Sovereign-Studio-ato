import { describe, expect, it } from 'vitest';
import {
  assertDiffPreviewReady,
  buildGeneratedFileDiffItem,
  buildGeneratedFileDiffReport,
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
});
