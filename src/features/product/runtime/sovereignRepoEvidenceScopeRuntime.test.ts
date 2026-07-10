import { describe, expect, it } from 'vitest';
import {
  buildRepoEvidenceScopeKey,
  buildRepositoryTargetKey,
  isOpenHandsJobScopedToRepo,
  selectRepoScopedOpenHandsJob,
  selectRepositoryScopedPullRequestUrl,
} from './sovereignRepoEvidenceScopeRuntime';
import type { DevChatRepoSnapshot } from './devChatWorkerBridge';
import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';

function snapshot(overrides: Partial<DevChatRepoSnapshot> = {}): DevChatRepoSnapshot {
  return {
    owner: 'OuroborosCollective',
    repo: 'Sovereign-Studio-ato',
    name: 'Sovereign-Studio-ato',
    branch: 'main',
    repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
    fileCount: 1,
    files: [{ path: 'src/App.tsx', type: 'blob', size: 1 }],
    dirs: ['src'],
    lastFile: 'App.tsx',
    lastPath: 'src/App.tsx',
    truncated: false,
    ...overrides,
  };
}

function job(overrides: Partial<OpenHandsJobSnapshot> = {}): OpenHandsJobSnapshot {
  return {
    status: 'completed',
    repoUrl: 'https://github.com/ouroboroscollective/sovereign-studio-ato.git',
    branch: 'main',
    changedFiles: ['src/App.tsx'],
    events: [],
    ...overrides,
  };
}

describe('sovereignRepoEvidenceScopeRuntime', () => {
  it('builds separate repository and branch-scoped identities', () => {
    expect(buildRepositoryTargetKey(snapshot())).toBe('ouroboroscollective/sovereign-studio-ato');
    expect(buildRepoEvidenceScopeKey(snapshot())).toBe('https://github.com/ouroboroscollective/sovereign-studio-ato#main');
  });

  it('accepts equivalent GitHub URL spellings only for the same branch', () => {
    expect(isOpenHandsJobScopedToRepo(job(), snapshot())).toBe(true);
    expect(isOpenHandsJobScopedToRepo(job({ branch: 'feature/runtime' }), snapshot())).toBe(false);
  });

  it('rejects missing or foreign job scope instead of assuming ownership', () => {
    expect(selectRepoScopedOpenHandsJob(job({ repoUrl: undefined }), snapshot())).toBeUndefined();
    expect(selectRepoScopedOpenHandsJob(job({ repoUrl: 'https://github.com/OuroborosCollective/Other' }), snapshot())).toBeUndefined();
  });

  it('accepts only pull-request URLs belonging to the current repository target', () => {
    const target = buildRepositoryTargetKey(snapshot());
    expect(selectRepositoryScopedPullRequestUrl(
      'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/42',
      target,
    )).toContain('/pull/42');
    expect(selectRepositoryScopedPullRequestUrl(
      'https://github.com/OuroborosCollective/Other/pull/42',
      target,
    )).toBeUndefined();
    expect(selectRepositoryScopedPullRequestUrl('https://example.com/pull/42', target)).toBeUndefined();
  });
});
