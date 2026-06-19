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
    get length() {
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

function writeFailingStorage(): Storage {
  const values = new Map<string, string>();

  return {
    get length() {
      return values.size;
    },

    clear() {
      values.clear();
    },

    getItem(key: string) {
      return values.get(key) ?? null;
    },

    key(index: number) {
      return Array.from(values.keys())[index] ?? null;
    },

    removeItem(key: string) {
      values.delete(key);
    },

    setItem() {
      throw new Error('write blocked');
    },
  };
}

function noRemoveStorage(): Storage {
  const values = new Map<string, string>();

  return {
    get length() {
      return values.size;
    },

    clear() {
      values.clear();
    },

    getItem(key: string) {
      return values.get(key) ?? null;
    },

    key(index: number) {
      return Array.from(values.keys())[index] ?? null;
    },

    removeItem() {
      // intentionally broken storage: remove does nothing
    },

    setItem(key: string, value: string) {
      values.set(key, value);
    },
  };
}

function findFirstStorageKey(storage: Storage): string {
  const key = storage.key(0);
  if (!key) throw new Error('expected storage key to exist');
  return key;
}

describe('repo snapshot runtime bridge', () => {
  it('creates a valid repo snapshot without saving it', () => {
    const result = createRuntimeRepoSnapshot(validInput());

    expect(result.ok).toBe(true);
    expect(result.snapshot).toBeDefined();
    expect(result.snapshot?.repoUrl).toBe('https://github.com/owner/repo');
    expect(result.report.valid).toBe(true);
  });

  it('creates, saves, loads, and clears a valid repo snapshot through runtime exports', () => {
    const storage = createRuntimeMemoryStorage();
    const input = validInput();

    expect(createRuntimeRepoSnapshot(input).ok).toBe(true);

    const saved = saveRuntimeRepoSnapshot(storage, input);
    expect(saved.ok).toBe(true);
    expect(saved.snapshot?.repoUrl).toBe('https://github.com/owner/repo');

    const loaded = loadRuntimeRepoSnapshot(storage);
    expect(loaded.ok).toBe(true);
    expect(loaded.snapshot?.repoUrl).toBe('https://github.com/owner/repo');

    expect(clearRuntimeRepoSnapshot(storage)).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(false);
  });

  it('does not accept an empty repo snapshot through runtime bridge', () => {
    const result = createRuntimeRepoSnapshot({
      ...validInput(),
      repoStatus: 'empty',
      repoFiles: [],
    });

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(result.report.valid).toBe(false);
    expect(result.report.errors.join(' ')).toContain('repoFiles must contain at least one file');
  });

  it('does not create fake snapshots for invalid input objects', () => {
    const result = createRuntimeRepoSnapshot({
      repoUrl: '',
      repoBranch: '',
      repoStatus: '',
      repoFiles: [],
    });

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(result.report.errors).toContain('repoUrl is required.');
    expect(result.report.errors).toContain('repoBranch is required.');
    expect(result.report.errors).toContain('repoStatus is required.');
    expect(result.report.errors).toContain('repoFiles must contain at least one file.');
  });

  it('does not mutate storage when input validation fails', () => {
    const storage = createRuntimeMemoryStorage();

    const result = saveRuntimeRepoSnapshot(storage, {
      repoUrl: '',
      repoBranch: '',
      repoStatus: '',
      repoFiles: [],
    });

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(storage.length).toBe(0);
    expect(hasRuntimeRepoSnapshot(storage)).toBe(false);
  });

  it('validates runtime input before durable snapshot creation', () => {
    const report = validateRuntimeRepoSnapshotInput({
      repoUrl: 'not-a-url',
      repoBranch: 'main',
      repoStatus: 'loaded',
      repoFiles: [{ path: 'README.md', type: 'blob', size: 10 }],
    });

    expect(report.valid).toBe(true);
    expect(report.warnings).toContain('repoUrl is not a valid absolute URL.');
  });

  it('rejects non-object runtime input validation', () => {
    const report = validateRuntimeRepoSnapshotInput(null);

    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('runtime repo snapshot input must be an object');
  });

  it('rejects invalid repoFiles entries before durable creation', () => {
    const report = validateRuntimeRepoSnapshotInput({
      repoUrl: 'https://github.com/owner/repo',
      repoBranch: 'main',
      repoStatus: 'loaded',
      repoFiles: ['README.md'],
    });

    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('repoFiles[0] must be an object');
  });

  it('rejects loaded null snapshots', () => {
    const report = validateLoadedRuntimeRepoSnapshot(null);

    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('no valid durable repo snapshot found');
  });

  it('rejects loaded non-object snapshots', () => {
    const report = validateLoadedRuntimeRepoSnapshot('bad-snapshot');

    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('loaded runtime repo snapshot must be an object');
  });

  it('returns false and a report when storage is missing', () => {
    const saved = saveRuntimeRepoSnapshot(null, validInput());
    const loaded = loadRuntimeRepoSnapshot(null);
    const cleared = clearRuntimeRepoSnapshotResult(null);

    expect(saved.ok).toBe(false);
    expect(saved.snapshot).toBeNull();
    expect(saved.report.errors.join(' ')).toContain('storage is required');

    expect(loaded.ok).toBe(false);
    expect(loaded.snapshot).toBeNull();
    expect(loaded.report.errors.join(' ')).toContain('storage is required');

    expect(cleared.ok).toBe(false);
    expect(cleared.report.errors.join(' ')).toContain('storage is required');
  });

  it('detects readable and writable memory storage', () => {
    const storage = createRuntimeMemoryStorage();
    const status = inspectRuntimeRepoSnapshotStorage(storage);

    expect(status.available).toBe(true);
    expect(status.readable).toBe(true);
    expect(status.writable).toBe(true);
    expect(status.clearable).toBe(true);
    expect(status.errors).toHaveLength(0);
  });

  it('storage inspection does not leave probe keys behind', () => {
    const storage = createRuntimeMemoryStorage({ alpha: '1' });

    const beforeLength = storage.length;
    const status = inspectRuntimeRepoSnapshotStorage(storage);

    expect(status.available).toBe(true);
    expect(status.errors).toHaveLength(0);
    expect(storage.length).toBe(beforeLength);
    expect(storage.getItem('alpha')).toBe('1');
  });

  it('detects unreadable storage', () => {
    const status = inspectRuntimeRepoSnapshotStorage(readFailingStorage());

    expect(status.available).toBe(true);
    expect(status.readable).toBe(false);
    expect(status.errors.join(' ')).toContain('storage is not readable');
  });

  it('detects unwritable storage', () => {
    const status = inspectRuntimeRepoSnapshotStorage(writeFailingStorage());

    expect(status.available).toBe(true);
    expect(status.readable).toBe(true);
    expect(status.writable).toBe(false);
    expect(status.errors.join(' ')).toContain('storage is not writable');
  });

  it('detects storage that cannot remove probe keys cleanly', () => {
    const status = inspectRuntimeRepoSnapshotStorage(noRemoveStorage());

    expect(status.available).toBe(true);
    expect(status.readable).toBe(true);
    expect(status.writable).toBe(true);
    expect(status.clearable).toBe(false);
    expect(status.warnings.join(' ')).toContain('storage probe cleanup verification failed');
  });

  it('does not save when storage is not writable', () => {
    const result = saveRuntimeRepoSnapshot(writeFailingStorage(), validInput());

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(result.report.summary).toContain('storage is not writable');
  });

  it('does not load when storage is not readable', () => {
    const result = loadRuntimeRepoSnapshot(readFailingStorage());

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(result.report.summary).toContain('storage is not readable');
  });

  it('reports no snapshot before save', () => {
    const storage = createRuntimeMemoryStorage();

    const result = loadRuntimeRepoSnapshot(storage);

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(result.report.summary).toContain('no valid durable repo snapshot found');
  });

  it('reports snapshot presence through hasRuntimeRepoSnapshot()', () => {
    const storage = createRuntimeMemoryStorage();

    expect(hasRuntimeRepoSnapshot(storage)).toBe(false);

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    expect(hasRuntimeRepoSnapshot(storage)).toBe(true);

    clearRuntimeRepoSnapshot(storage);

    expect(hasRuntimeRepoSnapshot(storage)).toBe(false);
  });

  it('rejects corrupted persisted snapshot on load', () => {
    const storage = createRuntimeMemoryStorage();

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    const key = findFirstStorageKey(storage);
    storage.setItem(key, JSON.stringify({ broken: true }));

    const loaded = loadRuntimeRepoSnapshot(storage);
    const gate = getRuntimeRepoSnapshotReadyGate(storage);

    expect(loaded.ok).toBe(false);
    expect(loaded.snapshot).toBeNull();
    expect(gate.ready).toBe(false);
  });

  it('returns detailed health without a snapshot', () => {
    const storage = createRuntimeMemoryStorage();

    const health = getRuntimeRepoSnapshotHealth(storage);

    expect(health.ok).toBe(false);
    expect(health.storage.available).toBe(true);
    expect(health.storage.readable).toBe(true);
    expect(health.storage.writable).toBe(true);
    expect(health.hasSnapshot).toBe(false);
    expect(health.snapshotValid).toBe(false);
    expect(health.report.summary).toContain('no valid durable repo snapshot found');
  });

  it('returns storage failure health when storage is unreadable', () => {
    const health = getRuntimeRepoSnapshotHealth(readFailingStorage());

    expect(health.ok).toBe(false);
    expect(health.storage.available).toBe(true);
    expect(health.storage.readable).toBe(false);
    expect(health.hasSnapshot).toBe(false);
    expect(health.snapshotValid).toBe(false);
    expect(health.report.summary).toContain('storage is not readable');
  });

  it('returns green health after valid save', () => {
    const storage = createRuntimeMemoryStorage();

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    const health = getRuntimeRepoSnapshotHealth(storage);

    expect(health.ok).toBe(true);
    expect(health.storage.available).toBe(true);
    expect(health.storage.readable).toBe(true);
    expect(health.storage.writable).toBe(true);
    expect(health.hasSnapshot).toBe(true);
    expect(health.snapshotValid).toBe(true);
    expect(health.report.valid).toBe(true);
  });

  it('returns not-ready gate before snapshot exists', () => {
    const storage = createRuntimeMemoryStorage();

    const gate = getRuntimeRepoSnapshotReadyGate(storage);

    expect(gate.ready).toBe(false);
    expect(gate.result.ok).toBe(false);
    expect(gate.health.hasSnapshot).toBe(false);
    expect(gate.reason).toContain('no valid durable repo snapshot found');
  });

  it('returns not-ready gate when storage is missing', () => {
    const gate = getRuntimeRepoSnapshotReadyGate(null);

    expect(gate.ready).toBe(false);
    expect(gate.result.ok).toBe(false);
    expect(gate.health.storage.available).toBe(false);
    expect(gate.reason).toContain('storage is required');
  });

  it('returns not-ready gate when storage is unreadable', () => {
    const gate = getRuntimeRepoSnapshotReadyGate(readFailingStorage());

    expect(gate.ready).toBe(false);
    expect(gate.result.ok).toBe(false);
    expect(gate.health.storage.readable).toBe(false);
    expect(gate.reason).toContain('storage is not readable');
  });

  it('returns ready gate after valid save', () => {
    const storage = createRuntimeMemoryStorage();

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    const gate = getRuntimeRepoSnapshotReadyGate(storage);

    expect(gate.ready).toBe(true);
    expect(gate.result.ok).toBe(true);
    expect(gate.health.ok).toBe(true);
    expect(gate.reason).toBe('runtime repo snapshot ready.');
  });

  it('assertRuntimeRepoSnapshotReady returns invalid result when not ready', () => {
    const storage = createRuntimeMemoryStorage();

    const result = assertRuntimeRepoSnapshotReady(storage);

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(result.report.valid).toBe(false);
  });

  it('assertRuntimeRepoSnapshotReady returns loaded snapshot when ready', () => {
    const storage = createRuntimeMemoryStorage();

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    const result = assertRuntimeRepoSnapshotReady(storage);

    expect(result.ok).toBe(true);
    expect(result.snapshot?.repoUrl).toBe('https://github.com/owner/repo');
    expect(result.report.valid).toBe(true);
  });

  it('clearRuntimeRepoSnapshotResult verifies clear result', () => {
    const storage = createRuntimeMemoryStorage();

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    const cleared = clearRuntimeRepoSnapshotResult(storage);

    expect(cleared.ok).toBe(true);
    expect(cleared.report.valid).toBe(true);
    expect(cleared.report.summary).toBe('runtime repo snapshot cleared.');
    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(false);
  });

  it('clearRuntimeRepoSnapshotResult fails when storage cannot remove saved snapshot', () => {
    const storage = noRemoveStorage();

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    const cleared = clearRuntimeRepoSnapshotResult(storage);

    expect(cleared.ok).toBe(false);
    expect(cleared.report.valid).toBe(false);
    expect(cleared.report.summary).toContain('snapshot could not be cleared');
    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(true);
  });

  it('boolean clearRuntimeRepoSnapshot mirrors clear report result', () => {
    const storage = createRuntimeMemoryStorage();

    expect(clearRuntimeRepoSnapshot(null)).toBe(false);

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    expect(clearRuntimeRepoSnapshot(storage)).toBe(true);
  });

  it('createRuntimeMemoryStorage supports seed, set, get, remove, key, and clear', () => {
    const storage = createRuntimeMemoryStorage({
      alpha: '1',
      beta: '2',
    });

    expect(storage.length).toBe(2);
    expect(storage.getItem('alpha')).toBe('1');
    expect(storage.getItem('missing')).toBeNull();
    expect(storage.key(0)).toBe('alpha');

    storage.setItem('gamma', '3');
    expect(storage.getItem('gamma')).toBe('3');
    expect(storage.length).toBe(3);

    storage.removeItem('beta');
    expect(storage.getItem('beta')).toBeNull();
    expect(storage.length).toBe(2);

    storage.clear();
    expect(storage.length).toBe(0);
  });

  it('createRuntimeMemoryStorage coerces keys and values like browser Storage', () => {
    const storage = createRuntimeMemoryStorage();

    storage.setItem('count', String(7));
    storage.setItem(String(123), String(true));

    expect(storage.getItem('count')).toBe('7');
    expect(storage.getItem('123')).toBe('true');
  });

  it('normalizes input before creating durable snapshot', () => {
    const result = createRuntimeRepoSnapshot({
      repoUrl: '  https://github.com/owner/repo  ',
      repoBranch: '  main  ',
      repoStatus: '  loaded  ',
      repoFiles: [{ path: 'README.md', type: 'blob' as const, size: 10 }],
    });

    expect(result.ok).toBe(true);
    expect(result.snapshot?.repoUrl).toBe('https://github.com/owner/repo');
    expect(result.snapshot?.repoBranch).toBe('main');
    expect(result.snapshot?.repoStatus).toBe('loaded');
  });
});
