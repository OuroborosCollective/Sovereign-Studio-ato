import { describe, expect, it } from 'vitest';
import {
  builderPublishLabel,
  deriveBuilderContainerState,
  isPlaceholderMission,
  normalizeBuilderMission,
} from './builderContainerRuntime';

const baseInput = {
  repoReady: true,
  runtimeBusy: false,
  repoBusy: false,
  isPublishing: false,
  mission: 'Verbessere die Android Repo-Eingabe mit sichtbaren Labels, PAT-Hilfe und Tests.',
  sovereignSummary: 'Summary',
  sovereignPreview: '{ }',
};

describe('builderContainerRuntime', () => {
  it('normalizes mission text', () => {
    expect(normalizeBuilderMission('  build   this\nnow  ')).toBe('build this now');
  });

  it('detects placeholder missions', () => {
    expect(isPlaceholderMission(' README   +   Update History ')).toBe(true);
    expect(isPlaceholderMission(baseInput.mission)).toBe(false);
  });

  it('allows generation and publishing when ready', () => {
    const state = deriveBuilderContainerState(baseInput);
    expect(state.canGenerate).toBe(true);
    expect(state.canPublish).toBe(true);
    expect(state.hasMission).toBe(true);
    expect(state.hasSummary).toBe(true);
    expect(state.hasPreview).toBe(true);
  });

  it('blocks placeholder mission production', () => {
    const state = deriveBuilderContainerState({ ...baseInput, mission: 'README + Update History' });
    expect(state.canGenerate).toBe(false);
    expect(state.canPublish).toBe(false);
    expect(state.disabledReason).toContain('Platzhalter');
  });

  it('blocks when repo is not ready', () => {
    const state = deriveBuilderContainerState({ ...baseInput, repoReady: false });
    expect(state.canGenerate).toBe(false);
    expect(state.canPublish).toBe(false);
    expect(state.disabledReason).toContain('not ready');
  });

  it('blocks when runtime is busy', () => {
    const state = deriveBuilderContainerState({ ...baseInput, runtimeBusy: true });
    expect(state.canGenerate).toBe(false);
    expect(state.disabledReason).toContain('runtime');
  });

  it('blocks empty mission', () => {
    const state = deriveBuilderContainerState({ ...baseInput, mission: '   ' });
    expect(state.canGenerate).toBe(false);
    expect(state.disabledReason).toContain('Mission');
  });

  it('labels publishing state', () => {
    expect(builderPublishLabel(false)).toBe('Draft PR erstellen');
    expect(builderPublishLabel(true)).toBe('Draft PR läuft...');
  });
});
