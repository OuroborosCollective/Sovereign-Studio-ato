import { describe, expect, it } from 'vitest';
import {
  buildSovereignPackageFromRepoFiles,
  hasConcreteSovereignMission,
  resolveAutonomousSovereignMission,
  summarizeSovereignPackage,
} from './sovereignPackageFromRepoFiles';
import type { Card, ProjectSettings } from '../types';

const cards: Card[] = [{ id: 'card-docs', title: 'Docs', body: 'Update README and runtime docs.' }];

const settings: ProjectSettings = {
  repoMode: 'monorepo',
  packageManager: 'pnpm',
  installStrategy: 'workspace',
  linter: 'auto',
  specialization: 'React Vite Android Router',
  maxFixLoops: 3,
};

const repoFiles = [
  { path: 'README.md', type: 'blob' as const },
  { path: 'package.json', type: 'blob' as const },
  { path: 'src/App.tsx', type: 'blob' as const },
  { path: 'src/global-runtime-monitor.tsx', type: 'blob' as const },
  { path: 'src/features/product/runtime/sovereignReleaseGuide.ts', type: 'blob' as const },
  { path: 'src/features/product/runtime/sovereignPackageFromRepoFiles.ts', type: 'blob' as const },
  { path: 'src/features/product/runtime/repoLaunchReadiness.ts', type: 'blob' as const },
  { path: 'src/features/product/runtime/repoLaunchReadiness.test.ts', type: 'blob' as const },
];

describe('sovereignPackageFromRepoFiles', () => {
  it('still requires loaded repo files', () => {
    expect(() => buildSovereignPackageFromRepoFiles({
      mission: 'Update README with current runtime setup',
      cards,
      settings,
      repoFiles: [],
    })).toThrow('Load a real repository tree');
  });

  it('turns default builder text into an executable autonomous mission', () => {
    expect(hasConcreteSovereignMission('README + Update History')).toBe(false);

    const mission = resolveAutonomousSovereignMission('README + Update History', repoFiles);

    expect(mission).toContain('autonome Runtime-Stabilisierung');
    expect(mission).toContain('wirklich geplanten Arbeitsschritten');
    expect(mission).toContain('src/global-runtime-monitor.tsx');
    expect(hasConcreteSovereignMission(mission)).toBe(true);
  });

  it('builds a guarded package from default builder text', () => {
    const pkg = buildSovereignPackageFromRepoFiles({
      mission: 'README + Update History',
      cards,
      settings,
      repoFiles,
    });

    expect(pkg.requestedWork).toBe('runtime-hardening');
    expect(pkg.brain.perception.intent).toContain('autonome Runtime-Stabilisierung');
    expect(pkg.brain.execution.patches.length).toBeGreaterThan(0);
  });

  it('builds brain-gated docs package from loaded repo files and concrete mission', () => {
    const pkg = buildSovereignPackageFromRepoFiles({
      mission: 'Update README and launch readiness docs with current runtime setup',
      cards,
      settings,
      repoFiles,
    });

    expect(pkg.files.map((file) => file.path)).toContain('README.md');
    expect(pkg.files.map((file) => file.path)).toContain('docs/LAUNCH_READINESS.md');
    expect(pkg.brain.execution.patches.length).toBeGreaterThan(0);
  });

  it('summarizes generated package for UI logs', () => {
    const oneFileRepo = [{ path: 'README.md', type: 'blob' as const }];
    const pkg = buildSovereignPackageFromRepoFiles({
      mission: 'Update README with current runtime setup',
      cards,
      settings,
      repoFiles: oneFileRepo,
    });

    const summary = summarizeSovereignPackage(pkg, oneFileRepo);
    expect(summary).toContain('Snapshot: 1 entries');
    expect(summary).toContain('Architecture:');
    expect(summary).toContain('Brain:');
    expect(summary).toContain('Files:');
  });
});
