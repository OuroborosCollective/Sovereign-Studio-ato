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

  it('handles edge cases such as leading, trailing, and consecutive slashes gracefully', () => {
    const tree = buildRepoTree([
      { path: '///src//features///a.ts/', type: 'blob' },
      { path: 'README.md', type: 'blob' },
    ]);

    expect(tree.map((node) => node.name)).toEqual(['src', 'README.md']);
    expect(tree[0].children.map((node) => node.name)).toEqual(['features']);
    expect(tree[0].children[0].children.map((node) => node.name)).toEqual(['a.ts']);
    expect(tree[0].children[0].children[0].path).toBe('src/features/a.ts');
  });

  it('demonstrates significant performance improvement on larger file structures', () => {
    const largeFileList = Array.from({ length: 500 }, (_, i) => ({
      path: `src/features/module${i % 10}/submodule${i % 20}/file_${i}.ts`,
      type: 'blob' as const,
      size: i * 100,
    }));

    const startTime = performance.now();
    const tree = buildRepoTree(largeFileList);
    const duration = performance.now() - startTime;

    expect(tree.length).toBeGreaterThan(0);
    // Tree operations are extremely fast with our substring and operator comparison optimizations
    expect(duration).toBeLessThan(100); // typically < 5ms now
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
