import { describe, expect, it } from 'vitest';

import runtimeDefault, {
  RuntimeCircuitBreaker,
  RuntimeIntelligence,
  RuntimeIntelligenceCore,
  RuntimeRepoSnapshotRuntime,
  RuntimeTelemetry,
  attachRepoSnapshotRuntime,
  clearRuntimeRepoSnapshot,
  coreRuntimeIntelligence,
  createRuntimeIntelligence,
  createRuntimeIntelligenceWithRepoSnapshot,
  createRuntimeRepoSnapshot,
  defaultTraceIdProvider,
  loadRuntimeRepoSnapshot,
  runGuardChain,
  runtimeIntelligence,
  saveRuntimeRepoSnapshot,
  type Guard,
  type RuntimeRepoSnapshotInput,
} from './index';

function validInput(): RuntimeRepoSnapshotInput {
  return {
    repoUrl: 'https://github.com/owner/repo',
    repoBranch: 'main',
    repoStatus: 'loaded',
    repoFiles: [
      {
        path: 'README.md',
        type: 'blob' as const,
        size: 10,
      },
    ],
  };
}

function invalidInput(): RuntimeRepoSnapshotInput {
  return {
    repoUrl: '',
    repoBranch: '',
    repoStatus: '',
    repoFiles: [],
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

function findFirstStorageKey(storage: Storage): string {
  const key = storage.key(0);
  if (!key) throw new Error('expected storage key to exist');
  return key;
}

describe('runtime index public API contract', () => {
  it('exports the augmented singleton as both named and default runtimeIntelligence', () => {
    expect(runtimeDefault).toBe(runtimeIntelligence);
    expect(runtimeIntelligence).toBe(coreRuntimeIntelligence);
    expect(runtimeIntelligence).toBeInstanceOf(RuntimeIntelligence);

    expect(typeof runtimeIntelligence.decide).toBe('function');
    expect(typeof runtimeIntelligence.withGuard).toBe('function');
    expect(typeof runtimeIntelligence.getRuntimeHealth).toBe('function');

    expect(runtimeIntelligence.createRepoSnapshot).toBe(createRuntimeRepoSnapshot);
    expect(runtimeIntelligence.saveRepoSnapshot).toBe(saveRuntimeRepoSnapshot);
    expect(runtimeIntelligence.loadRepoSnapshot).toBe(loadRuntimeRepoSnapshot);
    expect(runtimeIntelligence.clearRepoSnapshot).toBe(clearRuntimeRepoSnapshot);
  });

  it('keeps core runtime namespace aligned with direct runtime exports', () => {
    expect(RuntimeIntelligenceCore.RuntimeIntelligence).toBe(RuntimeIntelligence);
    expect(RuntimeIntelligenceCore.RuntimeCircuitBreaker).toBe(RuntimeCircuitBreaker);
    expect(RuntimeIntelligenceCore.RuntimeTelemetry).toBe(RuntimeTelemetry);
    expect(RuntimeIntelligenceCore.defaultTraceIdProvider).toBe(defaultTraceIdProvider);
    expect(RuntimeIntelligenceCore.runGuardChain).toBe(runGuardChain);
  });

  it('keeps repo snapshot namespace aligned with direct repo snapshot exports', () => {
    expect(RuntimeRepoSnapshotRuntime.createRuntimeRepoSnapshot).toBe(createRuntimeRepoSnapshot);
    expect(RuntimeRepoSnapshotRuntime.saveRuntimeRepoSnapshot).toBe(saveRuntimeRepoSnapshot);
    expect(RuntimeRepoSnapshotRuntime.loadRuntimeRepoSnapshot).toBe(loadRuntimeRepoSnapshot);
    expect(RuntimeRepoSnapshotRuntime.clearRuntimeRepoSnapshot).toBe(clearRuntimeRepoSnapshot);
  });

  it('exports usable core runtime factories and primitives', async () => {
    const runtime = createRuntimeIntelligence({
      traceIdProvider: () => 'public-core-trace',
    });

    const guard: Guard = {
      name: 'public-export-guard',
      check: async (ctx) => ({
        pass: true,
        guardName: 'public-export-guard',
        traceId: ctx.traceId,
        durationMs: 0,
      }),
    };

    const result = await runtime.withGuard('public-export-operation', async () => 'ok', [guard]);

    expect(runtime).toBeInstanceOf(RuntimeIntelligence);
    expect(result.result).toBe('ok');
    expect(result.guardResults).toHaveLength(1);

    const health = runtime.getRuntimeHealth();
    expect(health.traceId).toBe('public-core-trace');
    expect(['green', 'yellow', 'red']).toContain(health.status);
  });

  it('exports usable circuit breaker and telemetry classes', async () => {
    const telemetry = new RuntimeTelemetry({
      maxEvents: 2,
    });

    telemetry.track({
      name: 'first',
      properties: {},
      timestamp: 1,
      traceId: 't1',
    });

    telemetry.track({
      name: 'second',
      properties: {},
      timestamp: 2,
      traceId: 't2',
    });

    telemetry.track({
      name: 'third',
      properties: {},
      timestamp: 3,
      traceId: 't3',
    });

    expect(telemetry.peek().map((event) => event.name)).toEqual(['second', 'third']);
    expect(telemetry.snapshot().droppedEvents).toBe(1);

    const breaker = new RuntimeCircuitBreaker(1, 30000, 'public-breaker');

    await expect(
      breaker.call(async () => {
        throw new Error('boom');
      }),
    ).rejects.toThrow('boom');

    expect(breaker.getState()).toBe('open');
    expect(breaker.snapshot().name).toBe('public-breaker');
  });

  it('exports runGuardChain as a stable public helper', async () => {
    const guard: Guard = {
      name: 'index-guard',
      check: async (ctx) => ({
        pass: true,
        guardName: 'index-guard',
        traceId: ctx.traceId,
        durationMs: 0,
      }),
    };

    const result = await runGuardChain(
      {
        traceId: 'index-trace',
        timestamp: Date.now(),
      },
      {
        preFlight: [guard],
        main: [],
        postFlight: [],
      },
    );

    expect(result.pass).toBe(true);
    expect(result.results).toHaveLength(1);
  });

  it('exports defaultTraceIdProvider with the runtime trace format', () => {
    const id = defaultTraceIdProvider();

    expect(id).toMatch(/^rt-[a-z0-9]{8}$/);
  });
});

describe('runtime index repo snapshot exports', () => {
  it('uses repo snapshot runtime through the public runtime library entry', () => {
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();
    const input = validInput();

    expect(createRuntimeRepoSnapshot(input).ok).toBe(true);
    expect(saveRuntimeRepoSnapshot(storage, input).ok).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(true);
    expect(clearRuntimeRepoSnapshot(storage)).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(false);
  });

  it('attaches repo snapshot methods to runtimeIntelligence singleton', () => {
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();
    const input = validInput();

    expect(runtimeIntelligence.createRepoSnapshot(input).ok).toBe(true);
    expect(runtimeIntelligence.saveRepoSnapshot(storage, input).ok).toBe(true);
    expect(runtimeIntelligence.loadRepoSnapshot(storage).ok).toBe(true);
    expect(runtimeIntelligence.clearRepoSnapshot(storage)).toBe(true);
    expect(runtimeIntelligence.loadRepoSnapshot(storage).ok).toBe(false);
  });

  it('keeps default export repo snapshot helpers aligned with singleton helpers', () => {
    expect(runtimeDefault.createRepoSnapshot).toBe(runtimeIntelligence.createRepoSnapshot);
    expect(runtimeDefault.saveRepoSnapshot).toBe(runtimeIntelligence.saveRepoSnapshot);
    expect(runtimeDefault.loadRepoSnapshot).toBe(runtimeIntelligence.loadRepoSnapshot);
    expect(runtimeDefault.clearRepoSnapshot).toBe(runtimeIntelligence.clearRepoSnapshot);
  });

  it('creates fresh augmented runtime instances without sharing object identity', () => {
    const first = createRuntimeIntelligenceWithRepoSnapshot();
    const second = createRuntimeIntelligenceWithRepoSnapshot();

    expect(first).not.toBe(second);
    expect(first).not.toBe(runtimeIntelligence);
    expect(second).not.toBe(runtimeIntelligence);

    expect(first).toBeInstanceOf(RuntimeIntelligence);
    expect(second).toBeInstanceOf(RuntimeIntelligence);

    expect(typeof first.decide).toBe('function');
    expect(typeof first.getRuntimeHealth).toBe('function');
    expect(typeof first.saveRepoSnapshot).toBe('function');
    expect(typeof second.saveRepoSnapshot).toBe('function');
  });

  it('fresh augmented runtime instances can use repo snapshot helpers', () => {
    const runtime = createRuntimeIntelligenceWithRepoSnapshot();
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();
    const input = validInput();

    const saved = runtime.saveRepoSnapshot(storage, input);
    const loaded = runtime.loadRepoSnapshot(storage);

    expect(saved.ok).toBe(true);
    expect(loaded.ok).toBe(true);
    expect(loaded.snapshot?.repoUrl).toBe('https://github.com/owner/repo');

    expect(runtime.clearRepoSnapshot(storage)).toBe(true);
    expect(runtime.loadRepoSnapshot(storage).ok).toBe(false);
  });

  it('fresh augmented runtime instances can use isolated runtime config', () => {
    const runtime = createRuntimeIntelligenceWithRepoSnapshot({
      traceIdProvider: () => 'isolated-index-trace',
    });

    const health = runtime.getRuntimeHealth();

    expect(health.traceId).toBe('isolated-index-trace');
    expect(['green', 'yellow', 'red']).toContain(health.status);
    expect(runtime).not.toBe(runtimeIntelligence);
  });

  it('does not share circuit breaker object identity between fresh augmented runtime instances', () => {
    const first = createRuntimeIntelligenceWithRepoSnapshot();
    const second = createRuntimeIntelligenceWithRepoSnapshot();

    const firstBreaker = first.getCircuitBreaker('same-name');
    const secondBreaker = second.getCircuitBreaker('same-name');

    expect(firstBreaker).not.toBe(secondBreaker);
    expect(firstBreaker.getState()).toBe('closed');
    expect(secondBreaker.getState()).toBe('closed');
  });

  it('attachRepoSnapshotRuntime augments custom runtime-like targets in place', () => {
    const target = {
      label: 'custom-runtime',
      decide: () => 'decision',
    };

    const augmented = attachRepoSnapshotRuntime(target);
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();
    const input = validInput();

    expect(augmented).toBe(target);
    expect(augmented.label).toBe('custom-runtime');
    expect(augmented.decide()).toBe('decision');
    expect(augmented.createRepoSnapshot(input).ok).toBe(true);
    expect(augmented.saveRepoSnapshot(storage, input).ok).toBe(true);
    expect(augmented.loadRepoSnapshot(storage).ok).toBe(true);
    expect(augmented.clearRepoSnapshot(storage)).toBe(true);
  });

  it('attachRepoSnapshotRuntime is idempotent for repo snapshot helper identities', () => {
    const target = {
      label: 'idempotent-target',
    };

    const first = attachRepoSnapshotRuntime(target);
    const second = attachRepoSnapshotRuntime(first);

    expect(second).toBe(first);
    expect(second.createRepoSnapshot).toBe(createRuntimeRepoSnapshot);
    expect(second.saveRepoSnapshot).toBe(saveRuntimeRepoSnapshot);
    expect(second.loadRepoSnapshot).toBe(loadRuntimeRepoSnapshot);
    expect(second.clearRepoSnapshot).toBe(clearRuntimeRepoSnapshot);
  });

  it('exposes repo snapshot internals through RuntimeRepoSnapshotRuntime namespace', () => {
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();
    const input = validInput();

    const storageStatus = RuntimeRepoSnapshotRuntime.inspectRuntimeRepoSnapshotStorage(storage);
    expect(storageStatus.available).toBe(true);
    expect(storageStatus.readable).toBe(true);
    expect(storageStatus.writable).toBe(true);

    const saved = RuntimeRepoSnapshotRuntime.saveRuntimeRepoSnapshot(storage, input);
    expect(saved.ok).toBe(true);

    const health = RuntimeRepoSnapshotRuntime.getRuntimeRepoSnapshotHealth(storage);
    const gate = RuntimeRepoSnapshotRuntime.getRuntimeRepoSnapshotReadyGate(storage);

    expect(health.ok).toBe(true);
    expect(health.hasSnapshot).toBe(true);
    expect(gate.ready).toBe(true);
    expect(gate.reason).toBe('runtime repo snapshot ready.');
  });

  it('does not create fake snapshots through public index exports for invalid input', () => {
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();
    const created = createRuntimeRepoSnapshot(invalidInput());
    const saved = saveRuntimeRepoSnapshot(storage, invalidInput());

    expect(created.ok).toBe(false);
    expect(created.snapshot).toBeNull();

    expect(saved.ok).toBe(false);
    expect(saved.snapshot).toBeNull();

    expect(loadRuntimeRepoSnapshot(storage).ok).toBe(false);
    expect(storage.length).toBe(0);
  });

  it('does not create fake snapshots through augmented singleton for invalid input', () => {
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();

    const created = runtimeIntelligence.createRepoSnapshot(invalidInput());
    const saved = runtimeIntelligence.saveRepoSnapshot(storage, invalidInput());

    expect(created.ok).toBe(false);
    expect(created.snapshot).toBeNull();

    expect(saved.ok).toBe(false);
    expect(saved.snapshot).toBeNull();

    expect(runtimeIntelligence.loadRepoSnapshot(storage).ok).toBe(false);
    expect(storage.length).toBe(0);
  });

  it('reports storage write failure through public index exports', () => {
    const result = saveRuntimeRepoSnapshot(writeFailingStorage(), validInput());

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(result.report.summary).toContain('storage is not writable');
  });

  it('reports storage read failure through public index exports', () => {
    const result = loadRuntimeRepoSnapshot(readFailingStorage());

    expect(result.ok).toBe(false);
    expect(result.snapshot).toBeNull();
    expect(result.report.summary).toContain('storage is not readable');
  });

  it('rejects corrupted persisted snapshots through namespace ready gate', () => {
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();

    const saved = saveRuntimeRepoSnapshot(storage, validInput());
    expect(saved.ok).toBe(true);

    const key = findFirstStorageKey(storage);
    storage.setItem(key, JSON.stringify({ broken: true }));

    const loaded = loadRuntimeRepoSnapshot(storage);
    const gate = RuntimeRepoSnapshotRuntime.getRuntimeRepoSnapshotReadyGate(storage);

    expect(loaded.ok).toBe(false);
    expect(loaded.snapshot).toBeNull();
    expect(gate.ready).toBe(false);
  });

  it('keeps singleton repo snapshot helpers equal to direct public exports', () => {
    expect(runtimeIntelligence.createRepoSnapshot).toBe(createRuntimeRepoSnapshot);
    expect(runtimeIntelligence.saveRepoSnapshot).toBe(saveRuntimeRepoSnapshot);
    expect(runtimeIntelligence.loadRepoSnapshot).toBe(loadRuntimeRepoSnapshot);
    expect(runtimeIntelligence.clearRepoSnapshot).toBe(clearRuntimeRepoSnapshot);
  });
});
