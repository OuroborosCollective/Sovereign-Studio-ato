import { describe, expect, it } from 'vitest';
import {
  buildAutomationRunKey,
  decideSovereignAutomation,
  describeAutomationMode,
} from './sovereignAutomationMode';

describe('sovereignAutomationMode', () => {
  it('keeps manual mode passive', () => {
    expect(decideSovereignAutomation({
      mode: 'manual',
      repoReady: true,
      hasMission: true,
      hasToken: true,
      isBusy: false,
      hasPackage: false,
      nextAutoRunKey: 'x',
    })).toEqual({ shouldBuildPackage: false, shouldPublishDraftPr: false });
  });

  it('allows auto-review to build but not publish', () => {
    expect(decideSovereignAutomation({
      mode: 'auto-review',
      repoReady: true,
      hasMission: true,
      hasToken: false,
      isBusy: false,
      hasPackage: false,
      nextAutoRunKey: 'x',
    })).toMatchObject({ shouldBuildPackage: true, shouldPublishDraftPr: false });
  });

  it('requires a token for full auto draft PR', () => {
    expect(decideSovereignAutomation({
      mode: 'full-auto-draft-pr',
      repoReady: true,
      hasMission: true,
      hasToken: false,
      isBusy: false,
      hasPackage: false,
      nextAutoRunKey: 'x',
    }).blockedReason).toContain('PAT');
  });

  it('allows full auto draft PR when all inputs are ready', () => {
    expect(decideSovereignAutomation({
      mode: 'full-auto-draft-pr',
      repoReady: true,
      hasMission: true,
      hasToken: true,
      isBusy: false,
      hasPackage: true,
      nextAutoRunKey: 'x',
    })).toMatchObject({ shouldBuildPackage: false, shouldPublishDraftPr: true });
  });

  it('deduplicates identical automation snapshots', () => {
    const decision = decideSovereignAutomation({
      mode: 'auto-review',
      repoReady: true,
      hasMission: true,
      hasToken: false,
      isBusy: false,
      hasPackage: false,
      lastAutoRunKey: 'same',
      nextAutoRunKey: 'same',
    });
    expect(decision.shouldBuildPackage).toBe(false);
    expect(decision.blockedReason).toContain('already handled');
  });

  it('builds stable automation run keys', () => {
    const key = buildAutomationRunKey({
      mode: 'full-auto-draft-pr',
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repoBranch: 'main',
      mission: 'README + Update History',
      repoFileCount: 10,
    });
    expect(key).toContain('full-auto-draft-pr');
    expect(describeAutomationMode('manual')).toContain('Manual');
  });
});
