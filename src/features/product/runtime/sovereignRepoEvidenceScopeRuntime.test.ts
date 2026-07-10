import { describe, expect, it } from 'vitest';
import {
  buildRepoEvidenceScopeKey,
  buildRepositoryTargetKey,
  isSovereignAgentJobScopedToRepo,
  selectRepoScopedAgentJob,
  selectRepositoryScopedPullRequestUrl,
} from './sovereignRepoEvidenceScopeRuntime';
import type { DevChatRepoSnapshot } from './devChatWorkerBridge';
import type { SovereignAgentJobSnapshot } from './sovereignAgentRuntime';

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

function job(overrides: Partial<SovereignAgentJobSnapshot> = {}): SovereignAgentJobSnapshot {
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
    expect(isSovereignAgentJobScopedToRepo(job(), snapshot())).toBe(true);
    expect(isSovereignAgentJobScopedToRepo(job({ branch: 'feature/runtime' }), snapshot())).toBe(false);
  });

  it('rejects missing or foreign job scope instead of assuming ownership', () => {
    expect(selectRepoScopedAgentJob(job({ repoUrl: undefined }), snapshot())).toBeUndefined();
    expect(selectRepoScopedAgentJob(job({ repoUrl: 'https://github.com/OuroborosCollective/Other' }), snapshot())).toBeUndefined();
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
