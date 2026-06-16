import { describe, expect, it } from 'vitest';
import { buildRepoSignalsFromFiles } from './repoLaunchReadinessFromFiles';

const repoUrl = 'https://github.com/OuroborosCollective/Sovereign-Studio-ato';

describe('repoLaunchReadinessFromFiles', () => {
  it('detects docs, tests, workflows and runtime files from loaded repo paths', () => {
    const signals = buildRepoSignalsFromFiles(repoUrl, [
      { path: 'README.md', type: 'blob' },
      { path: 'LICENSE', type: 'blob' },
      { path: 'package.json', type: 'blob' },
      { path: '.github/workflows/ci.yml', type: 'blob' },
      { path: 'src/features/product/runtime/repoLaunchReadiness.test.ts', type: 'blob' },
      { path: 'src/features/product/brain/sovereignBrainContract.ts', type: 'blob' },
    ]);

    expect(signals.owner).toBe('OuroborosCollective');
    expect(signals.repo).toBe('Sovereign-Studio-ato');
    expect(signals.hasReadme).toBe(true);
    expect(signals.hasLicense).toBe(true);
    expect(signals.hasPackageJson).toBe(true);
    expect(signals.hasGithubWorkflows).toBe(true);
    expect(signals.hasTests).toBe(true);
    expect(signals.hasRuntimeValidation).toBe(true);
  });

  it('falls back to target repository when url is invalid', () => {
    const signals = buildRepoSignalsFromFiles('not-a-url', []);
    expect(signals.owner).toBe('target');
    expect(signals.repo).toBe('repository');
    expect(signals.hasReadme).toBe(false);
  });
});
