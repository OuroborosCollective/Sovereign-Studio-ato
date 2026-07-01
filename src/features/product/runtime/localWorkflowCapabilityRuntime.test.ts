import { describe, it, expect } from 'vitest';
import {
  evaluateLocalCapability,
  buildLocalWorkflowCapabilityState,
  createLocalWorkflowCapabilityStore,
  upsertLocalWorkflowCapabilityState,
  getLocalWorkflowCapabilityState,
  queryLocalExecutableStates,
  buildLocalCapabilityCheckSummary,
  validateLocalCapabilityCheckInput,
  type LocalCapabilityCheckInput,
} from './localWorkflowCapabilityRuntime';

const ALL_PASS: LocalCapabilityCheckInput = {
  inputsValidatable: true,
  stepsDeterministic: true,
  noSecretTokensRequired: true,
  noMandatoryLlmRoute: true,
  resultVerifiable: true,
  hasTestsOrReplayChecks: true,
};

const ALL_FAIL: LocalCapabilityCheckInput = {
  inputsValidatable: false,
  stepsDeterministic: false,
  noSecretTokensRequired: false,
  noMandatoryLlmRoute: false,
  resultVerifiable: false,
  hasTestsOrReplayChecks: false,
};

describe('localWorkflowCapabilityRuntime', () => {
  describe('evaluateLocalCapability', () => {
    it('returns localExecutable=true when all checks pass', () => {
      const result = evaluateLocalCapability(ALL_PASS);
      expect(result.localExecutable).toBe(true);
      expect(result.failedChecks).toHaveLength(0);
      expect(result.passedChecks).toHaveLength(6);
    });

    it('returns localExecutable=false when any check fails', () => {
      const result = evaluateLocalCapability({ ...ALL_PASS, hasTestsOrReplayChecks: false });
      expect(result.localExecutable).toBe(false);
      expect(result.failedChecks).toHaveLength(1);
    });

    it('returns localExecutable=false when all checks fail', () => {
      const result = evaluateLocalCapability(ALL_FAIL);
      expect(result.localExecutable).toBe(false);
      expect(result.failedChecks).toHaveLength(6);
      expect(result.passedChecks).toHaveLength(0);
    });

    it('includes summary text', () => {
      const resultPass = evaluateLocalCapability(ALL_PASS);
      expect(resultPass.summary).toContain('Lokal ausführbar');

      const resultFail = evaluateLocalCapability(ALL_FAIL);
      expect(resultFail.summary).toContain('Nicht lokal ausführbar');
    });

    it('fails specifically on secretTokens check', () => {
      const result = evaluateLocalCapability({ ...ALL_PASS, noSecretTokensRequired: false });
      expect(result.localExecutable).toBe(false);
      expect(result.failedChecks.some((c) => c.includes('Token'))).toBe(true);
    });

    it('fails specifically on mandatory LLM route check', () => {
      const result = evaluateLocalCapability({ ...ALL_PASS, noMandatoryLlmRoute: false });
      expect(result.localExecutable).toBe(false);
      expect(result.failedChecks.some((c) => c.includes('LLM'))).toBe(true);
    });
  });

  describe('buildLocalWorkflowCapabilityState', () => {
    it('builds state with evaluated result', () => {
      const state = buildLocalWorkflowCapabilityState('pat-abc', ALL_PASS, 1000);
      expect(state.patternId).toBe('pat-abc');
      expect(state.evaluatedAt).toBe(1000);
      expect(state.result.localExecutable).toBe(true);
    });

    it('throws when patternId is empty', () => {
      expect(() => buildLocalWorkflowCapabilityState('', ALL_PASS)).toThrow();
    });
  });

  describe('store operations', () => {
    it('creates an empty store', () => {
      const store = createLocalWorkflowCapabilityStore(1000);
      expect(store.version).toBe(1);
      expect(store.states).toHaveLength(0);
    });

    it('upserts a new state', () => {
      const store = createLocalWorkflowCapabilityStore(1000);
      const state = buildLocalWorkflowCapabilityState('pat-001', ALL_PASS, 1000);
      const next = upsertLocalWorkflowCapabilityState(store, state, 1000);
      expect(next.states).toHaveLength(1);
    });

    it('replaces existing state for same patternId', () => {
      const store = createLocalWorkflowCapabilityStore(1000);
      const state1 = buildLocalWorkflowCapabilityState('pat-001', ALL_PASS, 1000);
      const state2 = buildLocalWorkflowCapabilityState('pat-001', ALL_FAIL, 2000);
      const s1 = upsertLocalWorkflowCapabilityState(store, state1, 1000);
      const s2 = upsertLocalWorkflowCapabilityState(s1, state2, 2000);
      expect(s2.states).toHaveLength(1);
      expect(s2.states[0].result.localExecutable).toBe(false);
    });

    it('retrieves state by patternId', () => {
      const store = createLocalWorkflowCapabilityStore(1000);
      const state = buildLocalWorkflowCapabilityState('pat-001', ALL_PASS, 1000);
      const next = upsertLocalWorkflowCapabilityState(store, state, 1000);
      const found = getLocalWorkflowCapabilityState(next, 'pat-001');
      expect(found).not.toBeNull();
      expect(found!.patternId).toBe('pat-001');
    });

    it('returns null for missing patternId', () => {
      const store = createLocalWorkflowCapabilityStore(1000);
      expect(getLocalWorkflowCapabilityState(store, 'missing')).toBeNull();
    });

    it('queries only local-executable states', () => {
      const store = createLocalWorkflowCapabilityStore(1000);
      const passState = buildLocalWorkflowCapabilityState('pat-pass', ALL_PASS, 1000);
      const failState = buildLocalWorkflowCapabilityState('pat-fail', ALL_FAIL, 1000);
      const s1 = upsertLocalWorkflowCapabilityState(store, passState, 1000);
      const s2 = upsertLocalWorkflowCapabilityState(s1, failState, 1000);
      const executable = queryLocalExecutableStates(s2);
      expect(executable).toHaveLength(1);
      expect(executable[0].patternId).toBe('pat-pass');
    });
  });

  describe('buildLocalCapabilityCheckSummary', () => {
    it('returns a summary string', () => {
      const summary = buildLocalCapabilityCheckSummary(ALL_PASS);
      expect(typeof summary).toBe('string');
      expect(summary.length).toBeGreaterThan(0);
    });
  });

  describe('validateLocalCapabilityCheckInput', () => {
    it('validates all-boolean input', () => {
      const report = validateLocalCapabilityCheckInput(ALL_PASS);
      expect(report.valid).toBe(true);
      expect(report.errors).toHaveLength(0);
    });

    it('reports errors for non-boolean values', () => {
      const bad = { ...ALL_PASS, inputsValidatable: 'yes' as unknown as boolean };
      const report = validateLocalCapabilityCheckInput(bad);
      expect(report.valid).toBe(false);
      expect(report.errors.some((e) => e.includes('inputsValidatable'))).toBe(true);
    });
  });
});
