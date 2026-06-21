import { describe, expect, it } from 'vitest';

import {
  deriveReleaseGuideProgress,
  deriveReleaseGuideState,
  inferReleaseGuideTab,
  releaseGuideTabTestId,
  type ReleaseGuideInput,
} from './sovereignReleaseGuide';

function input(overrides: Partial<ReleaseGuideInput>): ReleaseGuideInput {
  return {
    lamp: 'green',
    title: 'Sovereign bereit',
    message: 'Repo laden, Auftrag analysieren und danach Auftrag starten.',
    action: 'Repo prüfen',
    thinking: false,
    source: 'runtime-shell',
    ...overrides,
  };
}

describe('sovereign release guide runtime', () => {
  it('detects the diff tab from package-ready guidance', () => {
    const state = deriveReleaseGuideState(input({
      title: 'Package bereit',
      message: 'Sovereign-Paket wurde erstellt. Diff und Files prüfen.',
      action: 'Weiter mit Diff',
    }));

    expect(state.targetTab).toBe('diff');
    expect(state.nextEnabled).toBe(true);
    expect(state.nextLabel).toBe('Weiter zu diff');
  });

  it('keeps progress on 5 percent steps', () => {
    const progress = deriveReleaseGuideProgress(input({
      title: 'Package bereit',
      action: 'Weiter mit Diff',
    }));

    expect(progress % 5).toBe(0);
    expect(progress).toBe(70);
  });

  it('detects repo and builder targets', () => {
    expect(inferReleaseGuideTab(input({ action: 'Load Repo' }))).toBe('repo');
    expect(inferReleaseGuideTab(input({ action: 'Auftrag analysieren' }))).toBe('builder');
  });

  it('locks next while thinking', () => {
    const state = deriveReleaseGuideState(input({
      action: 'Weiter mit Diff',
      thinking: true,
    }));

    expect(state.targetTab).toBe('diff');
    expect(state.nextEnabled).toBe(false);
    expect(state.waitingReason).toContain('Noch kein sicherer');
  });

  it('creates stable tab test ids', () => {
    expect(releaseGuideTabTestId('diff')).toBe('tabbar__diff');
    expect(releaseGuideTabTestId('repo')).toBe('tabbar__repo');
  });
});
