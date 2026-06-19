import { describe, expect, it } from 'vitest';
import { createRuntimeRepoSnapshot, saveRuntimeRepoSnapshot, loadRuntimeRepoSnapshot, clearRuntimeRepoSnapshot } from './index';

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

describe('runtime index repo snapshot exports', () => {
  it('uses repo snapshot runtime through the public runtime library entry', () => {
    const storage = memoryStorage();
    const input = {
      repoUrl: 'https://github.com/owner/repo',
      repoBranch: 'main',
      repoStatus: 'loaded',
      repoFiles: [{ path: 'README.md', type: 'blob' as const }],
    };

    expect(createRuntimeRepoSnapshot(input).ok).toBe(true);
    expect(saveRuntimeRepoSnapshot(storage, input).ok).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(true);
    expect(clearRuntimeRepoSnapshot(storage)).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(false);
  });
});
