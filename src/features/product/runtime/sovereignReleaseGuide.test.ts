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
  it('routes package-ready guidance to workflow instead of visible diff', () => {
    const state = deriveReleaseGuideState(input({
      title: 'Package bereit',
      message: 'Sovereign-Paket wurde erstellt. Diff und Files prüfen.',
      action: 'Weiter mit Diff',
    }));

    expect(state.targetTab).toBe('workflow');
    expect(state.nextEnabled).toBe(true);
    expect(state.nextLabel).toBe('Weiter');
    expect(state.helperMessage).toContain('sichtbaren Weiter-Button');
  });

  it('lets an explicit workflow action win over stale diff/package text', () => {
    const state = deriveReleaseGuideState(input({
      title: 'Package bereit',
      message: 'Sovereign-Paket wurde erstellt. Diff und Files prüfen.',
      action: 'Workflow prüfen',
      source: 'workflow',
    }));

    expect(state.targetTab).toBe('workflow');
    expect(state.nextEnabled).toBe(true);
    expect(state.nextLabel).toBe('Weiter');
    expect(state.progress).toBe(85);
  });

  it('does not claim that UI guidance auto-controls user navigation', () => {
    const state = deriveReleaseGuideState(input({
      title: 'Repository laden',
      message: 'Bitte GitHub-URL eingeben und Repository laden.',
      action: 'Load Repo',
    }));

    expect(state.helperMessage).toContain('sichtbare');
    expect(state.helperMessage).toContain('Button');
    expect(state.helperMessage).not.toContain('automatisch');
  });

  it('keeps progress on 5 percent steps without parking on diff', () => {
    const progress = deriveReleaseGuideProgress(input({
      title: 'Package bereit',
      message: 'Sovereign-Paket wurde erstellt. Diff und Files prüfen.',
      action: 'Weiter mit Diff',
    }));

    expect(progress % 5).toBe(0);
    expect(progress).toBe(80);
  });

  it('detects repo and builder targets without mixed default guidance', () => {
    expect(inferReleaseGuideTab(input({
      title: 'Repository laden',
      message: 'Bitte GitHub-URL eingeben und Repository laden.',
      action: 'Load Repo',
    }))).toBe('repo');

    expect(inferReleaseGuideTab(input({
      title: 'Bereit für Auftrag',
      message: 'Repository ist geladen. Auftrag eingeben und Package erstellen.',
      action: 'Auftrag analysieren',
    }))).toBe('builder');
  });

  it('locks next while thinking', () => {
    const state = deriveReleaseGuideState(input({
      title: 'Package bereit',
      message: 'Sovereign-Paket wurde erstellt. Diff und Files prüfen.',
      action: 'Weiter mit Diff',
      thinking: true,
    }));

    expect(state.targetTab).toBe('workflow');
    expect(state.nextEnabled).toBe(false);
    expect(state.waitingReason).toContain('Noch kein sicherer');
  });

  it('creates stable tab test ids', () => {
    expect(releaseGuideTabTestId('diff')).toBe('tabbar__diff');
    expect(releaseGuideTabTestId('repo')).toBe('tabbar__repo');
  });
});
