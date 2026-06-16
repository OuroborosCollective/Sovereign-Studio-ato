import { describe, expect, it } from 'vitest';
import {
  DEFAULT_TOOL_PROGRESS_RAIL,
  buildLaunchPackageMarkdown,
  evaluateRepoReadiness,
  parseRepoUrl,
  stableContextHash,
} from './repoLaunchReadiness';

describe('repoLaunchReadiness', () => {
  it('parses GitHub repository URLs safely', () => {
    expect(parseRepoUrl('https://github.com/OuroborosCollective/Sovereign-Studio-ato')).toEqual({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
    });
    expect(parseRepoUrl('https://github.com/OuroborosCollective/Repop1mm3l.git')).toEqual({
      owner: 'OuroborosCollective',
      repo: 'Repop1mm3l',
    });
    expect(parseRepoUrl('not-a-url')).toBeNull();
  });

  it('creates deterministic context hashes', () => {
    expect(stableContextHash('repo + constraints')).toBe(stableContextHash('repo + constraints'));
    expect(stableContextHash('repo + constraints')).not.toBe(stableContextHash('other'));
  });

  it('keeps the inherited tool progress rail stages', () => {
    expect(DEFAULT_TOOL_PROGRESS_RAIL.map((stage) => stage.id)).toEqual([
      'safe_repo_inspection',
      'task_extraction',
      'readiness_eval',
      'checklist_generation',
      'copywriting',
      'workflow_watch',
    ]);
  });

  it('scores a healthy repository above a risky repository', () => {
    const healthy = evaluateRepoReadiness({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
      recentCommitCount: 8,
      branchProtectionActive: true,
      hasReadme: true,
      hasLicense: true,
      hasTests: true,
      hasGithubWorkflows: true,
      hasRuntimeValidation: true,
    });

    const risky = evaluateRepoReadiness({
      owner: 'OuroborosCollective',
      repo: 'empty',
      recentCommitCount: 0,
      branchProtectionActive: false,
      hasReadme: false,
      hasLicense: false,
      hasTests: false,
      hasGithubWorkflows: false,
      hasRuntimeValidation: false,
    });

    expect(healthy.score).toBeGreaterThan(risky.score);
    expect(healthy.releaseStateReached).toBe(true);
    expect(risky.grade).toBe('BLOCKED');
  });

  it('builds launch package markdown with checklist and release state', () => {
    const report = evaluateRepoReadiness({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
      recentCommitCount: 8,
      branchProtectionActive: true,
      hasReadme: true,
      hasLicense: true,
      hasTests: true,
      hasGithubWorkflows: true,
      hasRuntimeValidation: true,
    });

    const markdown = buildLaunchPackageMarkdown({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
      hasReadme: true,
    }, report, 'ship docs safely');

    expect(markdown).toContain('Launch Readiness Package');
    expect(markdown).toContain('Owner Checklist');
    expect(markdown).toContain('RELEASE STATE REACHED');
  });
});
