import { describe, expect, it } from 'vitest';
import {
  SOVEREIGN_PRESET_ACTIONS,
  buildSovereignPresetActionPrompt,
  evaluateSovereignPresetActionGate,
  getSovereignPresetAction,
} from './sovereignPresetActionRuntime';

describe('sovereignPresetActionRuntime', () => {
  it('defines stable guided actions for common repo tasks', () => {
    expect(SOVEREIGN_PRESET_ACTIONS.length).toBeGreaterThanOrEqual(6);
    expect(SOVEREIGN_PRESET_ACTIONS.map((action) => action.id)).toContain('architecture_feature_suggestions');
    expect(SOVEREIGN_PRESET_ACTIONS.map((action) => action.id)).toContain('docs_architecture_sync');
  });

  it('blocks repo actions honestly when no repo is loaded', () => {
    const action = getSovereignPresetAction('architecture_feature_suggestions');
    const gate = evaluateSovereignPresetActionGate(action, { repoReady: false });

    expect(gate.canStart).toBe(false);
    expect(gate.reason).toMatch(/Repo-Kontext fehlt/);
  });

  it('blocks write presets when GitHub write access is missing', () => {
    const action = getSovereignPresetAction('docs_architecture_sync');
    const gate = evaluateSovereignPresetActionGate(action, {
      repoReady: true,
      githubWriteReady: false,
    });

    expect(gate.canStart).toBe(false);
    expect(gate.reason).toMatch(/GitHub-Schreibzugang fehlt/);
  });

  it('builds a deterministic prompt with route and runtime gate truth', () => {
    const action = getSovereignPresetAction('runtime_hardening');
    const prompt = buildSovereignPresetActionPrompt(action, {
      repoReady: true,
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      githubWriteReady: false,
      openhandsReady: false,
    });

    expect(prompt).toContain('Sovereign Preset: Runtime härten');
    expect(prompt).toContain('Repo: OuroborosCollective/Sovereign-Studio-ato · Branch: main');
    expect(prompt).toContain('Preset-Route: runtime_review');
    expect(prompt).toContain('GitHub Write: nein');
  });
});
