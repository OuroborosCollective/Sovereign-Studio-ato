import { describe, expect, it } from 'vitest';
import { clearRuntimeRepoSnapshot, createRuntimeRepoSnapshot, loadRuntimeRepoSnapshot, saveRuntimeRepoSnapshot } from './repoSnapshotRuntime';

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    removeItem: (key: string) => { values.delete(key); },
    setItem: (key: string, value: string) => { values.set(key, value); },
  };
}

describe('repo snapshot runtime bridge', () => {
  it('creates, saves, loads, and clears a valid repo snapshot through runtime exports', () => {
    const storage = memoryStorage();
    const input = {
      repoUrl: 'https://github.com/owner/repo',
      repoBranch: 'main',
      repoStatus: '1 echte Repo-Einträge geladen (main)',
      repoFiles: [{ path: 'README.md', type: 'blob' as const, size: 10 }],
    };

    expect(createRuntimeRepoSnapshot(input).ok).toBe(true);
    expect(saveRuntimeRepoSnapshot(storage, input).ok).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage)).toMatchObject({ ok: true, snapshot: { repoUrl: 'https://github.com/owner/repo' } });
    expect(clearRuntimeRepoSnapshot(storage)).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(false);
  });

  it('does not accept an empty repo snapshot through runtime bridge', () => {
    const result = createRuntimeRepoSnapshot({ repoUrl: 'https://github.com/owner/repo', repoBranch: 'main', repoStatus: 'empty', repoFiles: [] });
    expect(result.ok).toBe(false);
    expect(result.report.errors.join(' ')).toContain('repoFiles must not be empty');
  });
});
