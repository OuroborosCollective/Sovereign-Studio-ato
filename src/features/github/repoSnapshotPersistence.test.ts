import { describe, expect, it } from 'vitest';
import {
  clearDurableRepoSnapshot,
  createDurableRepoSnapshot,
  loadDurableRepoSnapshot,
  parseDurableRepoSnapshot,
  saveDurableRepoSnapshot,
  validateDurableRepoSnapshot,
} from './repoSnapshotPersistence';

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

describe('durable repo snapshot persistence', () => {
  it('stores and reloads a valid repo snapshot', () => {
    const storage = memoryStorage();
    const snapshot = createDurableRepoSnapshot({
      repoUrl: 'https://github.com/owner/repo',
      repoBranch: 'main',
      repoStatus: '1 echte Repo-Einträge geladen (main)',
      repoFiles: [{ path: 'README.md', type: 'blob', size: 10 }],
      savedAt: 123,
    });

    expect(validateDurableRepoSnapshot(snapshot).valid).toBe(true);
    expect(saveDurableRepoSnapshot(storage, snapshot)).toBe(true);
    expect(loadDurableRepoSnapshot(storage)).toMatchObject({ repoUrl: 'https://github.com/owner/repo', repoFiles: [{ path: 'README.md', type: 'blob', size: 10 }] });
  });

  it('rejects empty snapshots instead of restoring an empty repo state', () => {
    expect(parseDurableRepoSnapshot(JSON.stringify({ version: 1, repoUrl: 'https://github.com/owner/repo', repoBranch: 'main', repoStatus: 'empty', repoFiles: [], savedAt: 123 }))).toBeNull();
  });

  it('clears persisted snapshot only through explicit clear', () => {
    const storage = memoryStorage();
    const snapshot = createDurableRepoSnapshot({ repoUrl: 'https://github.com/owner/repo', repoBranch: 'main', repoStatus: 'ok', repoFiles: [{ path: 'src/App.tsx', type: 'blob' }] });
    expect(saveDurableRepoSnapshot(storage, snapshot)).toBe(true);
    clearDurableRepoSnapshot(storage);
    expect(loadDurableRepoSnapshot(storage)).toBeNull();
  });
});
