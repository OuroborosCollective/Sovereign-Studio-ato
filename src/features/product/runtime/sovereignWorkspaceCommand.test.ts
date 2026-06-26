import { describe, expect, it } from 'vitest';
import {
  SOVEREIGN_WORKSPACE_COMMAND_EVENT,
  SOVEREIGN_WORKSPACE_MENU,
  SOVEREIGN_WORKSPACE_TAB_IDS,
  createSovereignWorkspaceCommand,
  isSovereignWorkspaceCommandType,
  isSovereignWorkspaceTab,
  normalizeSovereignWorkspaceCommandDetail,
} from './sovereignWorkspaceCommand';

describe('sovereignWorkspaceCommand', () => {
  it('keeps the workspace command event stable', () => {
    expect(SOVEREIGN_WORKSPACE_COMMAND_EVENT).toBe('sovereign:release-guide-command');
  });

  it('keeps menu entries backed by allowed tabs only', () => {
    const allowed = new Set<string>(SOVEREIGN_WORKSPACE_TAB_IDS);
    const menuIds = SOVEREIGN_WORKSPACE_MENU.map((item) => item.id);

    expect(menuIds).toHaveLength(SOVEREIGN_WORKSPACE_MENU.length);
    expect(new Set(menuIds).size).toBe(menuIds.length);
    expect(menuIds).toEqual(expect.arrayContaining(['builder', 'repo', 'files', 'diff', 'workflow', 'repair', 'remote', 'memory', 'telemetry', 'monitor', 'health', 'runtime', 'coverage', 'findings']));

    for (const item of SOVEREIGN_WORKSPACE_MENU) {
      expect(allowed.has(item.id)).toBe(true);
      expect(item.label.trim().length).toBeGreaterThan(0);
      expect(item.hint.trim().length).toBeGreaterThan(0);
    }
  });

  it('validates workspace tabs and command types', () => {
    expect(isSovereignWorkspaceTab('builder')).toBe(true);
    expect(isSovereignWorkspaceTab('workflow')).toBe(true);
    expect(isSovereignWorkspaceTab('unknown')).toBe(false);
    expect(isSovereignWorkspaceTab('repo;alert(1)')).toBe(false);

    expect(isSovereignWorkspaceCommandType('next')).toBe(true);
    expect(isSovereignWorkspaceCommandType('confirm')).toBe(true);
    expect(isSovereignWorkspaceCommandType('delete')).toBe(false);
  });

  it('creates and normalizes safe command details only', () => {
    expect(createSovereignWorkspaceCommand('runtime')).toEqual({ type: 'next', targetTab: 'runtime' });
    expect(createSovereignWorkspaceCommand('repo', 'confirm')).toEqual({ type: 'confirm', targetTab: 'repo' });

    expect(normalizeSovereignWorkspaceCommandDetail({ targetTab: 'files', type: 'back' })).toEqual({ targetTab: 'files', type: 'back' });
    expect(normalizeSovereignWorkspaceCommandDetail({ targetTab: 'files', type: 'bad' })).toEqual({ targetTab: 'files', type: 'next' });
    expect(normalizeSovereignWorkspaceCommandDetail({ targetTab: 'not-a-tab', type: 'next' })).toBeNull();
    expect(normalizeSovereignWorkspaceCommandDetail(null)).toBeNull();
  });
});
