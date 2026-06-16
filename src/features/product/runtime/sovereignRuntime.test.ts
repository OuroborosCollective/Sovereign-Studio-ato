import { describe, expect, it } from 'vitest';
import {
  analyzeRepoArchitecture,
  buildSovereignImplementationPackage,
  buildWorkflowWatchSummary,
  runtimeAssertSovereignPackage,
  SOVEREIGN_LLM_ROUTES,
} from './sovereignRuntime';
import type { Card, ProjectSettings } from '../types';

const settings: ProjectSettings = {
  repoMode: 'monorepo',
  packageManager: 'pnpm',
  installStrategy: 'workspace',
  linter: 'auto',
  specialization: 'React Vite Capacitor Android GitHub Actions Free First Router',
  maxFixLoops: 3,
};

const cards: Card[] = [
  { id: 'card-1', title: 'README', body: 'Repository documentation' },
];

describe('sovereignRuntime', () => {
  it('keeps the real free-first provider order before fallbacks', () => {
    expect(SOVEREIGN_LLM_ROUTES.slice(0, 3).map((route) => route.id)).toEqual([
      'mlvoca',
      'pollinations',
      'optional-user-keys',
    ]);
    expect(SOVEREIGN_LLM_ROUTES.slice(3).map((route) => route.id)).toContain('ovh-anonymous-code-chat');
  });

  it('detects repository architecture from real tree paths', () => {
    const analysis = analyzeRepoArchitecture([
      'package.json',
      'vite.config.ts',
      'src/features/product/hooks/useProductMagic.ts',
      '.github/workflows/ci.yml',
      'android/app/build.gradle',
      'src/shared/utils/runtimeValidation.ts',
      'src/features/product/runtime/sovereignRuntime.test.ts',
    ]);

    expect(analysis.repoKind).toBe('react-vite-capacitor');
    expect(analysis.hasGithubWorkflows).toBe(true);
    expect(analysis.hasTests).toBe(true);
    expect(analysis.hasRuntimeValidation).toBe(true);
  });

  it('generates real README documentation files instead of only workflow preview', () => {
    const pkg = buildSovereignImplementationPackage({
      blueprint: 'README + Update History',
      cards,
      settings,
      selectedFilePath: 'src/App.tsx',
      repoPaths: [
        'package.json',
        'vite.config.ts',
        'src/features/product/hooks/useProductMagic.ts',
        '.github/workflows/ci.yml',
        'android/app/build.gradle',
      ],
      existingProviderOrder: ['mlvoca', 'pollinations', 'optional-user-keys'],
    });

    runtimeAssertSovereignPackage(pkg);

    expect(pkg.brain.execution.patches.length).toBeGreaterThan(0);
    expect(pkg.files.map((file) => file.path)).toContain('README.md');
    expect(pkg.files.map((file) => file.path)).toContain('docs/UPDATE_HISTORY.md');
    expect(pkg.files.map((file) => file.path)).toContain('docs/SOVEREIGN_RUNTIME.md');
    expect(pkg.files.map((file) => file.path)).toContain('docs/LAUNCH_READINESS.md');
    expect(pkg.files.map((file) => file.path)).toContain('generated/sovereign-product/workflow.ts');
  });

  it('builds visible workflow retry status with 66 second window', () => {
    const message = buildWorkflowWatchSummary(['CI:queued:pending', 'Typecheck:in_progress:pending'], 66, 2, 3);
    expect(message).toContain('2/3');
    expect(message).toContain('66s');
    expect(message).toContain('CI');
  });
});
