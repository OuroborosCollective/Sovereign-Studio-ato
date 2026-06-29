import { describe, expect, it } from 'vitest';
import {
  builderPublishLabel,
  deriveBuilderContainerState,
  deriveWorkspaceRuntimeState,
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

describe('deriveWorkspaceRuntimeState', () => {
  it('shows empty message for idle status', () => {
    const state = deriveWorkspaceRuntimeState({ status: 'idle' });
    expect(state.shortMessage).toBe('');
    expect(state.status).toBe('idle');
  });

  it('shows "Workspace gestartet" for queued', () => {
    const state = deriveWorkspaceRuntimeState({ status: 'queued' });
    expect(state.shortMessage).toBe('Workspace gestartet');
  });

  it('shows "Repo geklont · Tests laufen" for running without files', () => {
    const state = deriveWorkspaceRuntimeState({ status: 'running' });
    expect(state.shortMessage).toBe('Repo geklont · Tests laufen');
  });

  it('shows file count for running with files', () => {
    const state = deriveWorkspaceRuntimeState({ status: 'running', changedFilesCount: 5 });
    expect(state.shortMessage).toBe('Repo geklont · 5 Datei(en)');
  });

  it('shows "Draft PR bereit" for completed with draft pr url', () => {
    const state = deriveWorkspaceRuntimeState({
      status: 'completed',
      draftPrUrl: 'https://github.com/test/repo/pull/1',
    });
    expect(state.shortMessage).toBe('Draft PR bereit');
  });

  it('shows file count for completed without draft pr', () => {
    const state = deriveWorkspaceRuntimeState({ status: 'completed', changedFilesCount: 3 });
    expect(state.shortMessage).toBe('3 Änderung(en) fertig');
  });

  it('shows blocker message for failed status', () => {
    const state = deriveWorkspaceRuntimeState({
      status: 'failed',
      blocker: 'Build error in line 42',
    });
    expect(state.shortMessage).toContain('Blocker');
    expect(state.shortMessage).toContain('Build error');
  });

  it('truncates long blocker messages', () => {
    const longBlocker = 'This is a very long blocker message that exceeds the maximum length and should be truncated';
    const state = deriveWorkspaceRuntimeState({ status: 'blocked', blocker: longBlocker });
    expect(state.shortMessage.length).toBeLessThanOrEqual(60);
    expect(state.shortMessage).toContain('…');
  });

  it('shows "Workspace bereinigt" for cleaned status', () => {
    const state = deriveWorkspaceRuntimeState({ status: 'cleaned' });
    expect(state.shortMessage).toBe('Workspace bereinigt');
  });

  it('allows inspector for completed with safe https url', () => {
    const state = deriveWorkspaceRuntimeState({
      status: 'completed',
      workspaceInspectorUrl: 'https://workspace.example.com/view/123',
    });
    expect(state.canShowInspector).toBe(true);
    expect(state.inspectorUrl).toBe('https://workspace.example.com/view/123');
  });

  it('blocks inspector for blocked status', () => {
    const state = deriveWorkspaceRuntimeState({
      status: 'blocked',
      workspaceInspectorUrl: 'https://workspace.example.com/view/123',
    });
    expect(state.canShowInspector).toBe(false);
    expect(state.inspectorUrl).toBeUndefined();
  });

  it('blocks inspector for cleaned status', () => {
    const state = deriveWorkspaceRuntimeState({
      status: 'cleaned',
      workspaceInspectorUrl: 'https://workspace.example.com/view/123',
    });
    expect(state.canShowInspector).toBe(false);
    expect(state.inspectorUrl).toBeUndefined();
  });

  it('blocks inspector for http urls', () => {
    const state = deriveWorkspaceRuntimeState({
      status: 'completed',
      workspaceInspectorUrl: 'http://insecure.example.com/view',
    });
    expect(state.canShowInspector).toBe(false);
    expect(state.inspectorUrl).toBeUndefined();
  });

  it('never shows fake success without real result', () => {
    const state = deriveWorkspaceRuntimeState({ status: 'completed' });
    expect(state.shortMessage).toBe('Workspace abgeschlossen');
    expect(state.shortMessage).not.toBe('Erfolg!');
  });
});
