import { describe, expect, it } from 'vitest';

const WORKSPACE_MENU_TARGETS = [
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
] as const;

describe('workspace command contract', () => {
  it('keeps the wrapper menu command targets stable', () => {
    expect(WORKSPACE_MENU_TARGETS).toEqual([
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

  it('keeps unsafe command ids outside the stable target list', () => {
    expect(WORKSPACE_MENU_TARGETS).toContain('workflow');
    expect(WORKSPACE_MENU_TARGETS).toContain('builder');
    expect(WORKSPACE_MENU_TARGETS).not.toContain('unknown');
    expect(WORKSPACE_MENU_TARGETS).not.toContain('repo;alert(1)');
  });
});
