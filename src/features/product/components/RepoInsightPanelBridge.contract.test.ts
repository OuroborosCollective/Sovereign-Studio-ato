import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const BRIDGE_PATH = 'src/features/product/components/RepoInsightPanelBridge.tsx';

function readBridge(): string {
  expect(existsSync(BRIDGE_PATH)).toBe(true);
  return readFileSync(BRIDGE_PATH, 'utf8');
}

describe('RepoInsightPanelBridge workspace inspector contract', () => {
  it('renders the workspace inspector strip from runtime state before the panel', () => {
    const source = readBridge();

    expect(source).toContain('WorkspaceInspectorStrip');
    expect(source).toContain('workspaceInspector');
    expect(source).toContain('data-testid="workspace-inspector-strip"');
    expect(source).toContain('<WorkspaceInspectorStrip inspector={workspaceInspector} />');
    expect(source.indexOf('<WorkspaceInspectorStrip inspector={workspaceInspector} />')).toBeLessThan(
      source.indexOf('<RepoInsightPanel'),
    );
  });

  it('keeps the bridge UI passive and free of second-state persistence', () => {
    const source = readBridge();

    expect(source).not.toContain('localStorage');
    expect(source).not.toContain('sessionStorage');
    expect(source).not.toContain('window.dispatchEvent');
    expect(source).not.toContain('querySelector');
  });
});
