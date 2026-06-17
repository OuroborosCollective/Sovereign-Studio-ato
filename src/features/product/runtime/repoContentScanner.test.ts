import { describe, expect, it } from 'vitest';
import { scanRepoContent } from './repoContentScanner';

describe('repoContentScanner', () => {
  it('returns no findings for clean selected content', () => {
    const report = scanRepoContent([{ path: 'README.md', content: 'Hello world\nUse the app.' }]);

    expect(report.scannedFiles).toBe(1);
    expect(report.findings).toHaveLength(0);
    expect(report.summary).toContain('0 content finding');
  });

  it('detects TODO and placeholder markers with content-scanned confidence', () => {
    const report = scanRepoContent([{ path: 'src/app.ts', content: 'TODO improve this\nconst mode = "placeholder";' }]);

    expect(report.findings.map((finding) => finding.kind)).toEqual(['todo', 'placeholder']);
    expect(report.findings.every((finding) => finding.confidence === 'content-scanned')).toBe(true);
  });

  it('reports oversized selected content without scanning line details', () => {
    const report = scanRepoContent([{ path: 'large.txt', content: 'x'.repeat(260_000) }]);

    expect(report.findings).toHaveLength(1);
    expect(report.findings[0].kind).toBe('large-content');
  });
});
