import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const HOOK_PATH = 'src/features/product/hooks/useRepoInsightBridge.ts';

function readHook(): string {
  expect(existsSync(HOOK_PATH)).toBe(true);
  return readFileSync(HOOK_PATH, 'utf8');
}

describe('useRepoInsightBridge workspace inspector contract', () => {
  it('keeps the workspace inspector runtime attached to the repo insight bridge', () => {
    const hook = readHook();

    expect(hook).toContain('buildWorkspaceInspectorRuntime');
    expect(hook).toContain('WorkspaceInspectorRuntimeResult');
    expect(hook).toContain('workspaceInspector: WorkspaceInspectorRuntimeResult | null');
    expect(hook).toContain('workspaceInspector: state.workspaceInspector?.policy ?? null');
  });

  it('does not introduce App.tsx or DOM-query coupling', () => {
    const hook = readHook();

    expect(hook).not.toContain('querySelector');
    expect(hook).not.toContain('localStorage');
    expect(hook).not.toContain('sessionStorage');
    expect(hook).not.toContain('src/App.tsx');
  });
});
