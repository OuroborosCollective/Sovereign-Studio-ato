import { describe, expect, it } from 'vitest';

import {
  assertRuntimeRepoSnapshotReady,
  clearRuntimeRepoSnapshot,
  clearRuntimeRepoSnapshotResult,
  createRuntimeMemoryStorage,
  createRuntimeRepoSnapshot,
  getRuntimeRepoSnapshotHealth,
  getRuntimeRepoSnapshotReadyGate,
  hasRuntimeRepoSnapshot,
  inspectRuntimeRepoSnapshotStorage,
  loadRuntimeRepoSnapshot,
  saveRuntimeRepoSnapshot,
  validateLoadedRuntimeRepoSnapshot,
  validateRuntimeRepoSnapshotInput,
  type RuntimeRepoSnapshotInput,
} from './repoSnapshotRuntime';

function validInput(): RuntimeRepoSnapshotInput {
  return {
    repoUrl: 'https://github.com/owner/repo',
    repoBranch: 'main',
    repoStatus: '1 echte Repo-Einträge geladen (main)',
    repoFiles: [
      {
        path: 'README.md',
        type: 'blob' as const,
        size: 10,
      },
    ],
  };
}

function readFailingStorage(): Storage {
  const values = new Map<string, string>();

  return {
    get length(): number {
      throw new Error('read blocked');
    },

    clear() {
      values.clear();
    },

    getItem() {
      throw new Error('get blocked');
    },

    key() {
      throw new Error('key blocked');
    },

    removeItem(key: string) {
      values.delete(key);
    },

    setItem(key: string, value: string) {
      values.set(key, value);
    },
  };
}

describe('repoSnapshotRuntime', () => {
  it('creates durable repo snapshots', () => {
    const snapshot = createRuntimeRepoSnapshot(validInput());

    expect(snapshot.version).toBe(1);
    expect(snapshot.repoUrl).toBe('https://github.com/owner/repo');
    expect(snapshot.repoBranch).toBe('main');
    expect(snapshot.fileCount).toBe(1);
    expect(snapshot.repoFiles[0].path).toBe('README.md');
  });

  it('validates valid runtime repo snapshot input', () => {
    const report = validateRuntimeRepoSnapshotInput(validInput());

    expect(report.valid).toBe(true);
    expect(report.ready).toBe(true);
    expect(report.errors).toEqual([]);
  });

  it('rejects missing repo snapshot input fields', () => {
    const report = validateRuntimeRepoSnapshotInput({
      repoUrl: '',
      repoBranch: '',
      repoStatus: '',
      repoFiles: [],
    });

    expect(report.valid).toBe(false);
    expect(report.errors).toContain('repoUrl is required.');
    expect(report.errors).toContain('repoBranch is required.');
    expect(report.errors).toContain('repoStatus is required.');
  });

  it('saves and loads a runtime repo snapshot', () => {
    const storage = createRuntimeMemoryStorage();
    const report = saveRuntimeRepoSnapshot(validInput(), storage);
    const loaded = loadRuntimeRepoSnapshot(storage);

    expect(report.valid).toBe(true);
    expect(loaded?.repoUrl).toBe('https://github.com/owner/repo');
    expect(loaded?.fileCount).toBe(1);
    expect(hasRuntimeRepoSnapshot(storage)).toBe(true);
  });

  it('clears runtime repo snapshots', () => {
    const storage = createRuntimeMemoryStorage();
    saveRuntimeRepoSnapshot(validInput(), storage);

    expect(clearRuntimeRepoSnapshot(storage)).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage)).toBeNull();
    expect(clearRuntimeRepoSnapshotResult(storage).valid).toBe(true);
  });

  it('reports ready gate for saved repo snapshots', () => {
    const storage = createRuntimeMemoryStorage();
    saveRuntimeRepoSnapshot(validInput(), storage);

    const gate = getRuntimeRepoSnapshotReadyGate(storage);

    expect(gate.ready).toBe(true);
    expect(gate.report.ready).toBe(true);
  });

  it('throws when no runtime repo snapshot is ready', () => {
    const storage = createRuntimeMemoryStorage();

    expect(() => assertRuntimeRepoSnapshotReady(storage)).toThrow(
      'No valid runtime repo snapshot is loaded.',
    );
  });

  it('returns runtime snapshot health', () => {
    const storage = createRuntimeMemoryStorage();
    saveRuntimeRepoSnapshot(validInput(), storage);

    expect(getRuntimeRepoSnapshotHealth(storage).valid).toBe(true);
  });

  it('validates loaded unknown snapshots safely', () => {
    expect(validateLoadedRuntimeRepoSnapshot(null).valid).toBe(false);
    expect(validateLoadedRuntimeRepoSnapshot({}).valid).toBe(false);
    expect(validateLoadedRuntimeRepoSnapshot(createRuntimeRepoSnapshot(validInput())).valid).toBe(true);
  });

  it('inspects working memory storage', () => {
    const status = inspectRuntimeRepoSnapshotStorage(createRuntimeMemoryStorage());

    expect(status.available).toBe(true);
    expect(status.readable).toBe(true);
    expect(status.writable).toBe(true);
    expect(status.clearable).toBe(true);
    expect(status.errors).toEqual([]);
  });

  it('inspects failing storage without throwing', () => {
    const status = inspectRuntimeRepoSnapshotStorage(readFailingStorage());

    expect(status.available).toBe(true);
    expect(status.readable).toBe(false);
    expect(status.errors.length).toBeGreaterThan(0);
  });
});
