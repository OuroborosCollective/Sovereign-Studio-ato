import { describe, expect, it } from 'vitest';
import {
  assertBrownfieldReportValid,
  buildBrownfieldReport,
} from './brownfieldExplorer';

describe('brownfieldExplorer', () => {
  it('returns a partial critical report for an empty repo tree', () => {
    const report = buildBrownfieldReport({
      repoName: 'Empty Repo',
      branch: 'main',
      files: [],
      analyzedAt: 123,
    });

    expect(report.status).toBe('partial');
    expect(report.fileCount).toBe(0);
    expect(report.sourceFileCount).toBe(0);
    expect(report.testFileCount).toBe(0);
    expect(report.analyzedAt).toBe(123);
    expect(report.findings.some((finding) => finding.id === 'tree:empty-repo')).toBe(true);
    expect(report.findings.some((finding) => finding.id === 'tree:no-source-files')).toBe(true);
    expect(report.summary).toContain('Brownfield');
    expect(() => assertBrownfieldReportValid(report)).not.toThrow();
  });

  it('detects low test density from the loaded file tree only', () => {
    const report = buildBrownfieldReport({
      repoName: 'Sovereign-Studio-ato',
      branch: 'main',
      files: [
        'package.json',
        'pnpm-lock.yaml',
        'src/App.tsx',
        'src/main.tsx',
        'src/features/product/runtime/one.ts',
        'src/features/product/runtime/two.ts',
        'src/features/product/runtime/three.ts',
        'src/features/product/runtime/four.ts',
        'src/features/product/runtime/five.ts',
        'src/features/product/runtime/six.ts',
        'src/features/product/runtime/seven.ts',
        'src/features/product/runtime/eight.ts',
        'src/features/product/runtime/nine.ts',
        'src/features/product/runtime/one.test.ts',
      ],
    });

    expect(report.status).toBe('complete');
    expect(report.sourceFileCount).toBe(11);
    expect(report.testFileCount).toBe(1);
    expect(report.findings.some((finding) => finding.id === 'coverage:very-low')).toBe(true);
    expect(report.findings.every((finding) => finding.detail.toLowerCase().includes('token') === false)).toBe(true);
  });

  it('flags legacy naming and derives hotspots deterministically', () => {
    const report = buildBrownfieldReport({
      repoName: 'Legacy Repo',
      branch: 'develop',
      files: [
        './package.json',
        './pnpm-lock.yaml',
        './src/legacy/OldFeature.tsx',
        './src/features/product/runtime/current.ts',
        './src/features/product/runtime/current.test.ts',
        './src/archive/backup-widget.ts',
      ],
    });

    expect(report.repoName).toBe('Legacy Repo');
    expect(report.branch).toBe('develop');
    expect(report.findings.filter((finding) => finding.category === 'naming')).toHaveLength(2);
    expect(report.topHotspots).toContain('src/archive/backup-widget.ts');
    expect(report.topHotspots).toContain('src/legacy/OldFeature.tsx');
    expect(() => assertBrownfieldReportValid(report)).not.toThrow();
  });

  it('detects mixed state pattern signals without reading source content', () => {
    const report = buildBrownfieldReport({
      repoName: 'Mixed State Repo',
      branch: 'main',
      files: [
        'package.json',
        'yarn.lock',
        'src/store/user.slice.ts',
        'src/store/use-zustand-session.ts',
        'src/state/settings.atom.ts',
        'src/store/user.slice.test.ts',
      ],
    });

    const patternFinding = report.findings.find((finding) => finding.id === 'pattern:mixed-state-management');
    expect(patternFinding?.severity).toBe('warn');
    expect(patternFinding?.detail).toContain('Redux/Slices');
    expect(patternFinding?.detail).toContain('Zustand');
    expect(patternFinding?.detail).toContain('Jotai/Atoms');
  });

  it('flags oversized source directories and missing lockfiles', () => {
    const files = [
      'package.json',
      ...Array.from({ length: 85 }, (_, index) => `src/features/large/file-${index}.ts`),
      ...Array.from({ length: 10 }, (_, index) => `src/features/large/file-${index}.test.ts`),
    ];

    const report = buildBrownfieldReport({ repoName: 'Large Repo', branch: 'main', files });

    expect(report.findings.some((finding) => finding.id === 'dependency:no-lockfile')).toBe(true);
    expect(report.findings.some((finding) => finding.id === 'size:directory:src/features/large')).toBe(true);
    expect(report.score.total).toBeGreaterThan(0);
    expect(report.findings.length).toBeLessThanOrEqual(50);
  });

  it('normalizes invalid paths and falls back to safe names without network access', () => {
    const report = buildBrownfieldReport({
      repoName: '  ',
      branch: '',
      files: [
        'src/main.tsx',
        'src/main.tsx',
        '/absolute/path.ts',
        'src\\shared\\utils.test.ts',
        '',
      ],
      analyzedAt: -1,
    });

    expect(report.repoName).toBe('unknown-repo');
    expect(report.branch).toBe('main');
    expect(report.fileCount).toBe(2);
    expect(report.analyzedAt).toBe(0);
    expect(report.testFileCount).toBe(1);
    expect(report.sourceFileCount).toBe(1);
    expect(() => assertBrownfieldReportValid(report)).not.toThrow();
  });
});
