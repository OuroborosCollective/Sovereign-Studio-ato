import { describe, expect, it } from 'vitest';
import {
  buildOfflineCapabilityLanguageEvidence,
  classifyOfflineCapabilityIntent,
  decideSovereignCapabilityRoute,
} from './sovereignCapabilityRouter';
import {
  buildSovereignPresetActionSubmission,
  getSovereignPresetAction,
} from './sovereignPresetActionRuntime';

describe('docs preset direct patch entry', () => {
  it('routes the validated docs preset into direct patch before publication', () => {
    const submission = buildSovereignPresetActionSubmission(
      getSovereignPresetAction('docs_architecture_sync'),
      {
        repoReady: true,
        repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
        branch: 'main',
        githubWriteReady: true,
        agentReady: false,
      },
    );

    expect(classifyOfflineCapabilityIntent(submission)).toBe('direct_patch');

    const decision = decideSovereignCapabilityRoute({
      language: buildOfflineCapabilityLanguageEvidence(submission),
      repoReady: true,
      githubAccessState: 'ready',
      agentReady: false,
      directGitHubPatchReady: true,
      workspaceReady: false,
      hasActiveWorkerBlocker: false,
      hasPackage: false,
    });

    expect(decision.route).toBe('direct-github-patch');
    expect(decision.allowed).toBe(true);
    expect(decision.nextAction).toBe('run_direct_patch');
    expect(decision.blocker).toBeUndefined();
  });

  it('does not inject the terminal publication intent before a diff exists', () => {
    const submission = buildSovereignPresetActionSubmission(
      getSovereignPresetAction('docs_architecture_sync'),
      {
        repoReady: true,
        githubWriteReady: true,
        agentReady: false,
      },
    );

    expect(submission.toLowerCase()).not.toContain('draft pr');
    expect(submission.toLowerCase()).not.toContain('pull request');
    expect(submission).toContain('Direct-Patch-Diff');
  });
});
