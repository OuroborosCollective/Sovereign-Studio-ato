import { describe, expect, it } from 'vitest';
import { buildRepoTree, createRepoFilePrompt, hasRepoTreeEntries, summarizeRepoTreeSnapshot } from './repoTreeExplorerRuntime';
import type { DevChatRepoSnapshot } from './devChatWorkerBridge';

describe('repoTreeExplorerRuntime', () => {
  it('builds nested folder tree deterministically', () => {
    const tree = buildRepoTree([
      { path: 'src/App.tsx', type: 'blob' },
      { path: 'README.md', type: 'blob' },
      { path: 'src/features/a.ts', type: 'blob' },
    ]);

    expect(tree.map((node) => node.name)).toEqual(['src', 'README.md']);
    expect(tree[0].type).toBe('folder');
    expect(tree[0].children.map((node) => node.name)).toEqual(['features', 'App.tsx']);
  });

  it('keeps explicit tree entries with child files', () => {
    const tree = buildRepoTree([
      { path: 'src', type: 'tree' },
      { path: 'src/index.ts', type: 'blob' },
    ]);
    expect(tree).toHaveLength(1);
    expect(tree[0].children[0].path).toBe('src/index.ts');
  });

  it('creates a conscious composer prompt for file taps', () => {
    expect(createRepoFilePrompt('src/App.tsx')).toContain('src/App.tsx');
    expect(createRepoFilePrompt('src/App.tsx')).toContain('nächsten sicheren Änderungsschritt');
  });

  it('summarizes honest empty and loaded states', () => {
    expect(summarizeRepoTreeSnapshot(null)).toBe('Repo-Snapshot fehlt.');
    const snapshot: DevChatRepoSnapshot = {
      owner: 'o',
      repo: 'r',
      branch: 'main',
      name: 'r',
      repoUrl: 'https://github.com/o/r',
      fileCount: 1,
      files: [{ path: 'README.md', type: 'blob' }],
      dirs: [],
      truncated: true,
    };
    expect(summarizeRepoTreeSnapshot(snapshot)).toContain('o/r');
    expect(summarizeRepoTreeSnapshot(snapshot)).toContain('truncated');
    expect(hasRepoTreeEntries(snapshot)).toBe(true);
  });
});
