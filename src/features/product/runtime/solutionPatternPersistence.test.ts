import { describe, expect, it } from 'vitest';
import { createSolutionPatternStore } from './solutionPatternMemory';
import {
  SOLUTION_PATTERN_STORAGE_KEY,
  clearSolutionPatternStore,
  loadSolutionPatternStore,
  saveSolutionPatternStore,
} from './solutionPatternPersistence';

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (key: string) => data.get(key) ?? null,
    key: (index: number) => Array.from(data.keys())[index] ?? null,
    removeItem: (key: string) => { data.delete(key); },
    setItem: (key: string, value: string) => { data.set(key, value); },
  };
}

describe('solutionPatternPersistence', () => {
  it('saves and loads a valid local store', () => {
    const storage = memoryStorage();
    const store = createSolutionPatternStore(10);

    const saved = saveSolutionPatternStore(storage, store);
    expect(saved.ok).toBe(true);
    expect(storage.getItem(SOLUTION_PATTERN_STORAGE_KEY)).toBeTruthy();

    const loaded = loadSolutionPatternStore(storage, 20);
    expect(loaded.ok).toBe(true);
    expect(loaded.store.updatedAt).toBe(10);
  });

  it('falls back to an empty store for invalid saved content', () => {
    const storage = memoryStorage();
    storage.setItem(SOLUTION_PATTERN_STORAGE_KEY, '{');

    const loaded = loadSolutionPatternStore(storage, 20);
    expect(loaded.ok).toBe(false);
    expect(loaded.store.patterns).toEqual([]);
    expect(loaded.store.updatedAt).toBe(20);
  });

  it('clears local store content', () => {
    const storage = memoryStorage();
    saveSolutionPatternStore(storage, createSolutionPatternStore(10));

    const cleared = clearSolutionPatternStore(storage, 30);
    expect(cleared.ok).toBe(true);
    expect(storage.getItem(SOLUTION_PATTERN_STORAGE_KEY)).toBeNull();
    expect(cleared.store.updatedAt).toBe(30);
  });
});
