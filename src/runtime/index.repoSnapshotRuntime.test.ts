import { describe, expect, it } from 'vitest';

import runtimeDefault, {
  RuntimeCircuitBreaker,
  RuntimeIntelligence,
  RuntimeIntelligenceCore,
  RuntimeRepoSnapshotRuntime,
  RuntimeTelemetry,
  SovereignExecutorBridgeRuntime,
  SovereignInternalOperatorRuntime,
  attachRepoSnapshotRuntime,
  clearRuntimeRepoSnapshot,
  coreRuntimeIntelligence,
  createRuntimeIntelligence,
  createRuntimeIntelligenceWithRepoSnapshot,
  createRuntimeRepoSnapshot,
  decideSovereignExecutorBridgeRoute,
  decideSovereignInternalOperator,
  defaultTraceIdProvider,
  inspectRuntimeRepoSnapshotStorage,
  loadRuntimeRepoSnapshot,
  runGuardChain,
  runtimeIntelligence,
  saveRuntimeRepoSnapshot,
  validateRuntimeRepoSnapshotInput,
  type Guard,
  type RuntimeContext,
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

describe('runtime index repo snapshot exports', () => {
  it('keeps legacy runtime exports available', () => {
    expect(runtimeDefault).toBeDefined();
    expect(RuntimeCircuitBreaker).toBeDefined();
    expect(RuntimeIntelligence).toBeDefined();
    expect(RuntimeIntelligenceCore).toBeDefined();
    expect(RuntimeTelemetry).toBeDefined();
    expect(coreRuntimeIntelligence).toBeDefined();
    expect(runtimeIntelligence).toBeDefined();
    expect(createRuntimeIntelligence).toBeDefined();
    expect(defaultTraceIdProvider).toBeDefined();
    expect(runGuardChain).toBeDefined();
  });

  it('creates runtime intelligence with attached repo snapshot helpers', () => {
    const runtime = createRuntimeIntelligenceWithRepoSnapshot();

    expect(runtime).toBeDefined();
    expect(runtime.createRepoSnapshot).toBe(createRuntimeRepoSnapshot);
    expect(runtime.saveRepoSnapshot).toBe(saveRuntimeRepoSnapshot);
  });

  it('attaches repo snapshot runtime to an existing runtime object', () => {
    const runtime = createRuntimeIntelligence();
    const attached = attachRepoSnapshotRuntime(runtime);

    expect(attached).toBe(runtime);
    expect(attached.createRepoSnapshot).toBe(createRuntimeRepoSnapshot);
    expect(attached.saveRepoSnapshot).toBe(saveRuntimeRepoSnapshot);
  });

  it('exports sovereign operator and executor bridge runtime helpers', () => {
    const runtime = createRuntimeIntelligenceWithRepoSnapshot();

    expect(decideSovereignInternalOperator).toBeDefined();
    expect(decideSovereignExecutorBridgeRoute).toBeDefined();
    expect(SovereignInternalOperatorRuntime.decideSovereignInternalOperator).toBe(decideSovereignInternalOperator);
    expect(SovereignExecutorBridgeRuntime.decideSovereignExecutorBridgeRoute).toBe(decideSovereignExecutorBridgeRoute);
    expect(runtime.decideSovereignInternalOperator).toBe(decideSovereignInternalOperator);
    expect(runtime.decideSovereignExecutorBridgeRoute).toBe(decideSovereignExecutorBridgeRoute);
  });

  it('exports repo snapshot runtime namespace', () => {
    expect(RuntimeRepoSnapshotRuntime.createRuntimeRepoSnapshot(validInput()).fileCount).toBe(1);
    expect(RuntimeRepoSnapshotRuntime.validateRuntimeRepoSnapshotInput(validInput()).valid).toBe(true);
    expect(RuntimeRepoSnapshotRuntime.validateRuntimeRepoSnapshotInput(invalidInput()).valid).toBe(false);
  });

  it('saves, loads and clears through index exports', () => {
    const storage = RuntimeRepoSnapshotRuntime.createRuntimeMemoryStorage();

    expect(saveRuntimeRepoSnapshot(validInput(), storage).valid).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage)?.repoUrl).toBe('https://github.com/owner/repo');
    expect(clearRuntimeRepoSnapshot(storage)).toBe(true);
    expect(loadRuntimeRepoSnapshot(storage)).toBeNull();
  });

  it('keeps failing storage typed as Storage', () => {
    const status = inspectRuntimeRepoSnapshotStorage(readFailingStorage());

    expect(status.available).toBe(true);
    expect(status.readable).toBe(false);
    expect(status.errors.length).toBeGreaterThan(0);
  });

  it('supports guard typing through index exports', async () => {
    const guard: Guard = {
      name: 'index-guard',
      check: async (ctx: RuntimeContext) => ({
        pass: true,
        guardName: 'index-guard',
        traceId: ctx.traceId,
        durationMs: 0,
      }),
    };

    const result = await runGuardChain(
      { traceId: 'index-test', timestamp: Date.now() },
      { preFlight: [guard], main: [], postFlight: [] },
    );

    expect(result.pass).toBe(true);
  });
});
