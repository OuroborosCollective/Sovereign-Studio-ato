import { describe, expect, it } from 'vitest';
import {
  WORKSPACE_COMMAND_TABS,
  createWorkspaceCommandDetail,
  decideWorkspaceCommand,
  isWorkspaceCommandTab,
} from './workspaceCommandRuntime';

describe('workspaceCommandRuntime', () => {
  it('declares all workspace menu command targets', () => {
    expect(WORKSPACE_COMMAND_TABS).toEqual([
      'builder',
      'repo',
      'files',
      'diff',
      'workflow',
      'repair',
      'remote',
      'memory',
      'telemetry',
      'monitor',
      'health',
      'runtime',
      'coverage',
      'findings',
    ]);
  });

  it('narrows safe workspace command tab ids', () => {
    expect(isWorkspaceCommandTab('workflow')).toBe(true);
    expect(isWorkspaceCommandTab('builder')).toBe(true);
    expect(isWorkspaceCommandTab('unknown')).toBe(false);
    expect(isWorkspaceCommandTab('repo;alert(1)')).toBe(false);
  });

  it('passes wrapper menu commands through the central Runtime Intelligence library', () => {
    const decision = decideWorkspaceCommand('workflow');

    expect(decision.context.containerId).toBe('mobile-workbench');
    expect(decision.context.traceId).toMatch(/^rt-/);
    expect(decision.decision.action).toBe('continue');
    expect(decision.decision.lamp).toBe('green');
    expect(decision.decision.learnTag).toBe('workspace-command.work');
  });

  it('creates release-guide command details with runtime trace evidence', () => {
    const detail = createWorkspaceCommandDetail('health');

    expect(detail).toMatchObject({
      type: 'next',
      targetTab: 'health',
      runtimeContainerId: 'mobile-workbench',
      runtimeDecision: 'continue',
      runtimeLamp: 'green',
    });
    expect(detail.runtimeTraceId).toMatch(/^rt-/);
  });
});
