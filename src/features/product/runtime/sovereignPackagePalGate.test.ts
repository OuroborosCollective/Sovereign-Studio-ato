import { describe, expect, it } from 'vitest';
import { buildSovereignPackageFromRepoFiles } from './sovereignPackageFromRepoFiles';
import type { Card, ProjectSettings } from '../types';

const cards: Card[] = [{ id: 'card-runtime', title: 'Runtime', body: 'Runtime guard work.' }];

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
  { path: 'src/features/product/runtime/palRouter.ts', type: 'blob' as const },
];

describe('sovereignPackage PAL gate', () => {
  it('prevents package creation when the PAL runtime receives a stopper', () => {
    expect(() => buildSovereignPackageFromRepoFiles({
      mission: 'Implementiere Runtime Schutz mit Tests',
      cards,
      settings,
      repoFiles,
      palBlockers: ['runtime hold'],
    })).toThrow('PAL_BLOCKED_PACKAGE_BUILD');
  });

  it('continues package creation when PAL allows the mission', () => {
    const pkg = buildSovereignPackageFromRepoFiles({
      mission: 'Update README with current runtime setup',
      cards,
      settings,
      repoFiles,
    });

    expect(pkg.files.length).toBeGreaterThan(0);
  });
});
