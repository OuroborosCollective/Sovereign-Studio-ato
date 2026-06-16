import { describe, expect, it } from 'vitest';
import { buildSovereignBranchName, validatePublishableFiles } from '../../github/githubPackagePublisher';
import { buildRepoSignalsFromFiles } from './repoLaunchReadinessFromFiles';
import {
  DEFAULT_TOOL_PROGRESS_RAIL,
  buildLaunchPackageMarkdown,
  evaluateRepoReadiness,
} from './repoLaunchReadiness';
import {
  assertGeneratedPackageReady,
  getRepoSnapshotStatus,
} from './sovereignFunctionalGuards';
import { buildSovereignPackageFromRepoFiles } from './sovereignPackageFromRepoFiles';

const repoFiles = [
  { path: 'README.md', type: 'blob' as const },
  { path: 'package.json', type: 'blob' as const },
  { path: '.github/workflows/ci.yml', type: 'blob' as const },
  { path: 'src/features/product/runtime/sovereignRuntime.ts', type: 'blob' as const },
  { path: 'src/features/product/runtime/sovereignRuntime.test.ts', type: 'blob' as const },
];

describe('sovereign runtime structure', () => {
  it('connects repo snapshot, readiness, package guards and publisher validation', () => {
    const snapshot = getRepoSnapshotStatus(repoFiles);
    expect(snapshot.ready).toBe(true);

    const signals = buildRepoSignalsFromFiles('https://github.com/OuroborosCollective/Sovereign-Studio-ato', repoFiles);
    const report = evaluateRepoReadiness(signals);
    const markdown = buildLaunchPackageMarkdown(signals, report, 'README + Update History');
    expect(markdown).toContain('Launch Readiness Package');

    const pkg = buildSovereignPackageFromRepoFiles({
      mission: 'README + Update History',
      repoFiles,
    });
    expect(() => assertGeneratedPackageReady(pkg, repoFiles)).not.toThrow();
    expect(pkg.files.map((file) => file.path)).toContain('docs/LAUNCH_READINESS.md');

    const publishable = validatePublishableFiles(pkg.files);
    expect(publishable.length).toBe(pkg.files.length);
    expect(buildSovereignBranchName('sovereign/package', 'Sovereign Studio: docs', publishable)).toMatch(/^sovereign\/package\/[a-f0-9]{8}$/);
  });

  it('keeps the tool progress rail as the visible top-level workflow', () => {
    expect(DEFAULT_TOOL_PROGRESS_RAIL.map((stage) => stage.id)).toEqual([
      'safe_repo_inspection',
      'task_extraction',
      'readiness_eval',
      'checklist_generation',
      'copywriting',
      'workflow_watch',
    ]);
  });
});
