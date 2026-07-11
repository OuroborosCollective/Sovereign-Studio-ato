import { describe, expect, it } from 'vitest';
import {
  decideSovereignSideMenuDraftPr,
  decideSovereignSideMenuShare,
} from './sovereignSideMenuRuntime';

describe('sovereignSideMenuRuntime', () => {
  it('routes Draft PR through repo setup before any write surface', () => {
    expect(decideSovereignSideMenuDraftPr({
      repoReady: false,
      hasChangeEvidence: false,
      githubWriteReady: false,
      isPublishing: false,
    })).toMatchObject({
      state: 'repo-required',
      action: 'open-repo-setup',
      canAct: true,
    });
  });

  it('does not offer Draft PR publication without real change evidence', () => {
    expect(decideSovereignSideMenuDraftPr({
      repoReady: true,
      hasChangeEvidence: false,
      githubWriteReady: true,
      isPublishing: false,
    })).toMatchObject({
      state: 'evidence-required',
      action: 'none',
      canAct: false,
    });
  });

  it('opens secure GitHub access only after change evidence exists', () => {
    expect(decideSovereignSideMenuDraftPr({
      repoReady: true,
      hasChangeEvidence: true,
      githubWriteReady: false,
      isPublishing: false,
    })).toMatchObject({
      state: 'access-required',
      action: 'open-github-access',
      canAct: true,
    });
  });

  it('allows Draft PR publication only with complete runtime evidence', () => {
    expect(decideSovereignSideMenuDraftPr({
      repoReady: true,
      hasChangeEvidence: true,
      githubWriteReady: true,
      isPublishing: false,
    })).toMatchObject({
      state: 'ready',
      action: 'publish-draft-pr',
      canAct: true,
    });
  });

  it('prevents duplicate or parallel Draft PR actions', () => {
    expect(decideSovereignSideMenuDraftPr({
      repoReady: true,
      hasChangeEvidence: true,
      githubWriteReady: true,
      isPublishing: true,
    }).canAct).toBe(false);

    expect(decideSovereignSideMenuDraftPr({
      repoReady: true,
      hasChangeEvidence: true,
      githubWriteReady: true,
      isPublishing: false,
      draftPrUrl: 'https://github.com/example/repo/pull/1',
    })).toMatchObject({ state: 'already-exists', canAct: false });
  });

  it('does not present an empty chat export as functional', () => {
    expect(decideSovereignSideMenuShare(0)).toMatchObject({
      canShare: false,
      statusLabel: 'Noch leer',
    });
    expect(decideSovereignSideMenuShare(2)).toMatchObject({
      canShare: true,
      statusLabel: '2 Nachrichten',
    });
  });
});
