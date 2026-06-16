import { describe, expect, it } from 'vitest';
import {
  buildSovereignPackageFromRepoFiles,
  summarizeSovereignPackage,
} from './sovereignPackageFromRepoFiles';
import type { Card, ProjectSettings } from '../types';

const cards: Card[] = [{ id: 'card-docs', title: 'Docs', body: 'Update README and runtime docs.' }];

const settings: ProjectSettings = {
  repoMode: 'monorepo',
  packageManager: 'pnpm',
  installStrategy: 'workspace',
  linter: 'auto',
  specialization: 'React Vite Capacitor Android GitHub Actions Free First Router',
  maxFixLoops: 3,
};

describe('sovereignPackageFromRepoFiles', () => {
  it('builds brain-gated docs package from loaded repo files', () => {
    const pkg = buildSovereignPackageFromRepoFiles({
      mission: 'README + Update History',
      cards,
      settings,
      repoFiles: [
        { path: 'README.md', type: 'blob' },
        { path: 'package.json', type: 'blob' },
        { path: '.github/workflows/ci.yml', type: 'blob' },
        { path: 'src/features/product/runtime/repoLaunchReadiness.ts', type: 'blob' },
        { path: 'src/features/product/runtime/repoLaunchReadiness.test.ts', type: 'blob' },
      ],
    });

    expect(pkg.files.map((file) => file.path)).toContain('README.md');
    expect(pkg.files.map((file) => file.path)).toContain('docs/LAUNCH_READINESS.md');
    expect(pkg.brain.execution.patches.length).toBeGreaterThan(0);
  });

  it('summarizes generated package for UI logs', () => {
    const pkg = buildSovereignPackageFromRepoFiles({
      mission: 'README + Update History',
      cards,
      settings,
      repoFiles: [{ path: 'README.md', type: 'blob' }],
    });

    const summary = summarizeSovereignPackage(pkg);
    expect(summary).toContain('Architecture:');
    expect(summary).toContain('Brain:');
    expect(summary).toContain('Files:');
  });
});
