import { describe, expect, it } from 'vitest';
import {
  assertGeneratedPackageReady,
  assertLoadedRepoSnapshot,
  assertSafeGeneratedFiles,
  buildRepoSnapshotSummary,
  getRepoSnapshotStatus,
} from './sovereignFunctionalGuards';
import type { SovereignImplementationPackage } from './sovereignRuntime';

function packageWithFiles(paths: string[]): SovereignImplementationPackage {
  return {
    architecture: {
      summary: 'node repo, README=yes, workflows=yes, tests=yes, runtime=yes',
      repoKind: 'node',
      hasReadme: true,
      hasGithubWorkflows: true,
      hasTests: true,
      hasRuntimeValidation: true,
      suggestedTargets: [],
      riskNotes: [],
    },
    brain: {
      perception: { domain: 'repo', intent: 'docs', architecture: 'node', confidence: 0.8 },
      analysis: { severity: 'medium', issues: [], rootCause: 'test', systemicRisk: 'test' },
      plan: { strategy: 'test', phases: [], estimatedComplexity: 'medium' },
      execution: { patches: [], integrationNotes: 'test', testStrategy: 'test' },
      learning: { patterns: [], rules: [], architectureUpgrade: 'test' },
    },
    files: paths.map((path) => ({ path, content: `content for ${path}`, reason: 'test' })),
    suggestions: [],
    providerRoutes: [{ id: 'mlvoca', label: 'Mlvoca', status: 'primary', requiresApiKey: false, requiresUserOptIn: false }],
    requestedWork: 'readme-docs',
  };
}

describe('sovereignFunctionalGuards', () => {
  it('requires a loaded repo snapshot with files', () => {
    expect(getRepoSnapshotStatus([]).ready).toBe(false);
    expect(() => assertLoadedRepoSnapshot([])).toThrow('Load a real repository tree');
    expect(() => assertLoadedRepoSnapshot([{ path: 'src', type: 'tree' }])).toThrow('contains no files');
    expect(() => assertLoadedRepoSnapshot([{ path: 'README.md', type: 'blob' }])).not.toThrow();
  });

  it('blocks unsafe generated output paths', () => {
    expect(() => assertSafeGeneratedFiles([{ path: '.env', content: 'x', reason: 'bad' }])).toThrow('Forbidden');
    expect(() => assertSafeGeneratedFiles([{ path: '../README.md', content: 'x', reason: 'bad' }])).toThrow('Invalid');
    expect(() => assertSafeGeneratedFiles([{ path: 'README.md', content: '', reason: 'bad' }])).toThrow('empty');
  });

  it('requires docs packages to contain the cemented docs file set', () => {
    const complete = packageWithFiles([
      'README.md',
      'docs/UPDATE_HISTORY.md',
      'docs/SOVEREIGN_RUNTIME.md',
      'docs/LAUNCH_READINESS.md',
    ]);
    expect(() => assertGeneratedPackageReady(complete, [{ path: 'README.md', type: 'blob' }])).not.toThrow();

    const incomplete = packageWithFiles(['README.md']);
    expect(() => assertGeneratedPackageReady(incomplete, [{ path: 'README.md', type: 'blob' }])).toThrow('missing required files');
  });

  it('summarizes repo snapshots for UI logs', () => {
    expect(buildRepoSnapshotSummary([
      { path: 'README.md', type: 'blob' },
      { path: 'src', type: 'tree' },
    ])).toBe('Snapshot: 2 entries (1 files, 1 folders).');
  });
});
