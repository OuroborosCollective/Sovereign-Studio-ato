/**
 * Runtime Intelligence Library Tests
 */

import { describe, expect, it, beforeEach } from 'vitest';

import {
  RuntimeCircuitBreaker,
  RuntimeIntelligence,
  RuntimeTelemetry,
  createRuntimeIntelligence,
  defaultTraceIdProvider,
  runGuardChain,
  runtimeIntelligence,
  type FullPipelineBridge,
  type Guard,
  type RuntimeContext,
  type RuntimeGuardResult,
} from './RuntimeIntelligence';

import { createBaselineContainerDecisionRules } from '../features/product/runtime/containerDecisionBaselineRules';

function createValidBridge(): FullPipelineBridge {
  return {
    repoToBuilder: {
      repoReady: true,
      fileCount: 42,
      repoUrl: 'https://github.com/owner/repo',
      branch: 'main',
      tokenInLogs: false,
    },
    builderToGeneratedFiles: {
      mission: 'Add new feature',
      isPlaceholder: false,
      repoSnapshotReady: true,
      packageHasFiles: true,
      filesActionable: true,
      planOnlyOnly: false,
    },
    generatedFilesToDiff: {
      packageExists: true,
      pathsValid: true,
      sourcesLoaded: true,
      isNewFile: false,
    },
    filesToDraftPR: {
      selfReviewAccepted: true,
      actionableOutput: true,
      planOnlyOnly: false,
      tokenPresent: true,
      repoParsed: true,
      branchNonceSafe: true,
      secretsInLogs: false,
    },
    workflowToFindings: {
      commitSha: 'abc123',
      workflowResultValid: true,
      redStatus: false,
      greenStatus: true,
      staleResult: false,
    },
    remoteMemoryToPatternMemory: {
      gatewayConfigValid: true,
      contributorId: 'user-123',
      collectionName: 'my-patterns',
      workspaceId: 'ws-456',
      deleteConfirmationsComplete: true,
      sharedPatternDetected: false,
    },
    telemetryToCoach: {
      eventValid: true,
      noSecrets: true,
      stagesKnown: ['repo', 'builder', 'pr'],
      latestByStageConsistent: true,
      noisyEventsCount: 3,
    },
  };
}

function createInvalidBridge(): FullPipelineBridge {
  return {
    repoToBuilder: {
      repoReady: false,
      fileCount: 0,
      repoUrl: 'invalid-url',
      branch: '',
      tokenInLogs: true,
    },
    builderToGeneratedFiles: {
      mission: '',
      isPlaceholder: true,
      repoSnapshotReady: false,
      packageHasFiles: false,
      filesActionable: false,
      planOnlyOnly: false,
    },
    generatedFilesToDiff: {
      packageExists: false,
      pathsValid: false,
      sourcesLoaded: false,
      isNewFile: false,
    },
    filesToDraftPR: {
      selfReviewAccepted: false,
      actionableOutput: false,
      planOnlyOnly: true,
      tokenPresent: false,
      repoParsed: false,
      branchNonceSafe: false,
      secretsInLogs: true,
    },
    workflowToFindings: {
      commitSha: null,
      workflowResultValid: false,
      redStatus: true,
      greenStatus: false,
      staleResult: true,
    },
    remoteMemoryToPatternMemory: {
      gatewayConfigValid: false,
      contributorId: null,
      collectionName: null,
      workspaceId: null,
      deleteConfirmationsComplete: false,
      sharedPatternDetected: true,
    },
    telemetryToCoach: {
      eventValid: false,
      noSecrets: false,
      stagesKnown: [],
      latestByStageConsistent: false,
      noisyEventsCount: 15,
    },
  };
}

describe('RuntimeIntelligence', () => {
  let runtime: RuntimeIntelligence;
  let baselineRules: ReturnType<typeof createBaselineContainerDecisionRules>;

  beforeEach(() => {
    runtime = createRuntimeIntelligence();
    baselineRules = createBaselineContainerDecisionRules();
  });

  describe('trace ID generation', () => {
    it('generates unique trace IDs', () => {
      const id1 = RuntimeIntelligence.createTraceId();
      const id2 = RuntimeIntelligence.createTraceId();

      expect(id1).not.toBe(id2);
      expect(typeof id1).toBe('string');
      expect(id1.length).toBeGreaterThan(5);
    });

    it('defaultTraceIdProvider returns stable runtime trace format', () => {
      const id = defaultTraceIdProvider();

      expect(id).toMatch(/^rt-[a-z0-9]{8}$/);
    });

    it('supports injectable trace ID provider', () => {
      let callCount = 0;

      const customProvider = () => {
        callCount += 1;
        return `custom-trace-${callCount}`;
      };

      const runtimeWithCustom = createRuntimeIntelligence({
        traceIdProvider: customProvider,
      });

      const first = runtimeWithCustom.decide('repo-snapshot', 'test', baselineRules);
      const second = runtimeWithCustom.decide('repo-snapshot', 'test', baselineRules);

      expect(callCount).toBe(2);
      expect(first.context.traceId).toBe('custom-trace-1');
      expect(second.context.traceId).toBe('custom-trace-2');
    });

    it('keeps withGuard on the same inherited trace path', async () => {
      let callCount = 0;

      const runtimeWithCustom = createRuntimeIntelligence({
        traceIdProvider: () => {
          callCount += 1;
          return `guard-trace-${callCount}`;
        },
      });

      let guardTrace = '';

      const guard: Guard = {
        name: 'trace-guard',
        check: async (ctx) => {
          guardTrace = ctx.traceId;

          return {
            pass: true,
            guardName: 'trace-guard',
            traceId: ctx.traceId,
            durationMs: 0,
          };
        },
      };

      const result = await runtimeWithCustom.withGuard(
        'trace-operation',
        async () => 'ok',
        [guard],
      );

      expect(result.result).toBe('ok');
      expect(guardTrace).toBe('guard-trace-1');
      expect(callCount).toBe(1);
    });
  });

  describe('decide()', () => {
    it('makes container decisions with telemetry', () => {
      const result = runtime.decide('repo-snapshot', 'repo snapshot ready', baselineRules);

      expect(result.decision).toBeDefined();
      expect(result.decision.containerId).toBe('repo-snapshot');
      expect(result.context.traceId).toBeDefined();
      expect(typeof result.confidence).toBe('number');
      expect(result.confidence).toBeGreaterThanOrEqual(0);
      expect(result.confidence).toBeLessThanOrEqual(1);
    });

    it('returns matched signals and explanation metadata', () => {
      const result = runtime.decide('repo-snapshot', 'repo snapshot review needed', baselineRules);

      expect(Array.isArray(result.matchedSignals)).toBe(true);
      expect(result.explanation).toBeDefined();
      expect(Array.isArray(result.explanation.matchedSignals)).toBe(true);
      expect(Array.isArray(result.explanation.alternatives)).toBe(true);
      expect(typeof result.explanation.confidenceReason).toBe('string');
      expect(typeof result.explanation.inputTruncated).toBe('boolean');
      expect(typeof result.explanation.inputLength).toBe('number');
      expect(typeof result.explanation.normalizedInputLength).toBe('number');
    });

    it('keeps explanation matched signals aligned with top-level matched signals', () => {
      const result = runtime.decide('repo-snapshot', 'repo snapshot review needed', baselineRules);

      expect(result.explanation.matchedSignals).toEqual(result.matchedSignals);
    });

    it('returns learning influence as side-channel only', () => {
      const result = runtime.decide('repo-snapshot', 'repo snapshot ready', baselineRules);

      expect(result.learningInfluence).toBeDefined();
      expect(['confirm', 'caution', 'insufficient-data']).toContain(
        result.learningInfluence.recommendation,
      );
      expect(typeof result.learningInfluence.confidenceDelta).toBe('number');
      expect(typeof result.learningInfluence.reason).toBe('string');
      expect(result.confidence).toBeGreaterThanOrEqual(0);
      expect(result.confidence).toBeLessThanOrEqual(1);
    });

    it('truncates oversized visible text safely', () => {
      const smallRuntime = createRuntimeIntelligence({
        maxVisibleTextLength: 20,
      });

      const result = smallRuntime.decide(
        'repo-snapshot',
        'repo snapshot ready '.repeat(20),
        baselineRules,
      );

      expect(result.explanation.inputTruncated).toBe(true);
      expect(result.explanation.inputLength).toBeGreaterThan(20);
      expect(result.explanation.normalizedInputLength).toBeLessThanOrEqual(20);
    });

    it('normalizes non-useful whitespace without crashing decision path', () => {
      const result = runtime.decide('repo-snapshot', '\n\n\t   repo     snapshot     ready   ', baselineRules);

      expect(result.decision).toBeDefined();
      expect(result.explanation.normalizedInputLength).toBeGreaterThan(0);
    });

    it('handles empty rules without throwing', () => {
      const result = runtime.decide('repo-snapshot', 'repo snapshot ready', []);

      expect(result.decision).toBeDefined();
      expect(Array.isArray(result.matchedSignals)).toBe(true);
      expect(Array.isArray(result.explanation.alternatives)).toBe(true);
    });
  });

  describe('matchMobilePattern()', () => {
    it('matches active work pattern', () => {
      const result = runtime.matchMobilePattern('running build is busy in progress');

      expect(result.rule).toBeDefined();
      expect(result.rule.id).toBe('active-work');
      expect(result.score).toBeGreaterThan(0);
    });

    it('matches real stopper pattern', () => {
      const result = runtime.matchMobilePattern(
        'validation failed build failed critical blocker',
      );

      expect(result.rule).toBeDefined();
      expect(result.rule.id).toBe('real-stopper');
    });

    it('returns awaiting-intent as fallback', () => {
      const result = runtime.matchMobilePattern('   ');

      expect(result.rule).toBeDefined();
      expect(result.rule.id).toBe('awaiting-intent');
    });

    it('handles oversized mobile pattern input safely', () => {
      const smallRuntime = createRuntimeIntelligence({
        maxVisibleTextLength: 30,
      });

      const result = smallRuntime.matchMobilePattern(
        `${'noise '.repeat(100)} running build is busy in progress`,
      );

      expect(result.rule).toBeDefined();
    });
  });

  describe('validatePipeline()', () => {
    it('validates full pipeline bridge with valid data', () => {
      const result = runtime.validatePipeline(createValidBridge());

      expect(result.overallValid).toBe(true);
      expect(result.criticalErrors).toHaveLength(0);
    });

    it('detects critical errors in pipeline', () => {
      const result = runtime.validatePipeline(createInvalidBridge());

      expect(result.overallValid).toBe(false);
      expect(result.criticalErrors.length).toBeGreaterThan(0);
    });
  });

  describe('coverage', () => {
    it('returns coverage report', () => {
      const report = runtime.getCoverageReport();

      expect(report).toBeDefined();
      expect(Array.isArray(report.entries)).toBe(true);
      expect(report.entries.length).toBeGreaterThan(0);
    });

    it('has valid report structure', () => {
      const report = runtime.getCoverageReport();

      expect(typeof report.valid).toBe('boolean');
      expect(typeof report.summary).toBe('string');
      expect(typeof report.coveredCount).toBe('number');
      expect(typeof report.partialCount).toBe('number');
      expect(typeof report.missingCount).toBe('number');
    });

    it('returns coverage gaps as an array', () => {
      const gaps = runtime.getCoverageGaps();

      expect(Array.isArray(gaps)).toBe(true);
    });

    it('assertCoverageValid either passes or throws a real Error', () => {
      try {
        runtime.assertCoverageValid();
        expect(true).toBe(true);
      } catch (error) {
        expect(error).toBeInstanceOf(Error);
      }
    });
  });

  describe('learning stats', () => {
    it('returns learning statistics', () => {
      const stats = runtime.getLearningStats();

      expect(stats).toBeDefined();
      expect(typeof stats.totalSignals).toBe('number');
      expect(typeof stats.accepted).toBe('number');
      expect(typeof stats.rejected).toBe('number');
    });

    it('returns recent learning as an array', () => {
      const recent = runtime.getRecentLearning(5);

      expect(Array.isArray(recent)).toBe(true);
      expect(recent.length).toBeLessThanOrEqual(5);
    });

    it('clamps negative recent learning limit to empty result', () => {
      const recent = runtime.getRecentLearning(-1);

      expect(recent).toEqual([]);
    });
  });

  describe('circuit breaker integration', () => {
    it('creates circuit breaker', () => {
      const cb = runtime.getCircuitBreaker('test');

      expect(cb).toBeInstanceOf(RuntimeCircuitBreaker);
      expect(cb.getState()).toBe('closed');
    });

    it('returns same circuit breaker for same name', () => {
      const cb1 = runtime.getCircuitBreaker('test');
      const cb2 = runtime.getCircuitBreaker('test');

      expect(cb1).toBe(cb2);
    });

    it('returns different circuit breakers for different names', () => {
      const cb1 = runtime.getCircuitBreaker('test1');
      const cb2 = runtime.getCircuitBreaker('test2');

      expect(cb1).not.toBe(cb2);
    });

    it('returns circuit breaker snapshots', () => {
      runtime.getCircuitBreaker('snapshot-test');

      const snapshots = runtime.getCircuitBreakerSnapshots();
      const snapshot = snapshots.find((entry) => entry.name === 'snapshot-test');

      expect(snapshot).toBeDefined();
      expect(snapshot?.state).toBe('closed');
      expect(typeof snapshot?.failures).toBe('number');
      expect(typeof snapshot?.threshold).toBe('number');
      expect(typeof snapshot?.timeoutMs).toBe('number');
      expect(typeof snapshot?.halfOpenProbeInFlight).toBe('boolean');
    });

    it('resets named circuit breaker', async () => {
      const cb = runtime.getCircuitBreaker('reset-test', 1, 30000);

      await expect(
        cb.call(async () => {
          throw new Error('fail');
        }),
      ).rejects.toThrow('fail');

      expect(cb.getState()).toBe('open');

      runtime.resetCircuitBreaker('reset-test');

      expect(cb.getState()).toBe('closed');
      expect(cb.getFailureCount()).toBe(0);
    });
  });

  describe('runtime health', () => {
    it('returns a runtime health snapshot', () => {
      const health = runtime.getRuntimeHealth();

      expect(health).toBeDefined();
      expect(['green', 'yellow', 'red']).toContain(health.status);
      expect(typeof health.traceId).toBe('string');
      expect(typeof health.timestamp).toBe('number');
      expect(health.telemetry).toBeDefined();
      expect(Array.isArray(health.circuitBreakers)).toBe(true);
      expect(health.coverage).toBeDefined();
      expect(Array.isArray(health.coverage.gaps)).toBe(true);
      expect(health.learning).toBeDefined();
      expect(Array.isArray(health.reasons)).toBe(true);
    });

    it('reports open circuit breaker as degraded health', async () => {
      const degradedRuntime = createRuntimeIntelligence();
      const cb = degradedRuntime.getCircuitBreaker('health-open-test', 1, 30000);

      await expect(
        cb.call(async () => {
          throw new Error('boom');
        }),
      ).rejects.toThrow('boom');

      const health = degradedRuntime.getRuntimeHealth();

      expect(health.circuitBreakers.some((entry) => entry.name === 'health-open-test')).toBe(
        true,
      );
      expect(['yellow', 'red']).toContain(health.status);
      expect(health.reasons.length).toBeGreaterThan(0);
    });

    it('reports bounded telemetry drops in health reasons', () => {
      const telemetry = new RuntimeTelemetry({
        maxEvents: 1,
      });

      const boundedRuntime = createRuntimeIntelligence({
        telemetry,
      });

      boundedRuntime.decide('repo-snapshot', 'first', baselineRules);
      boundedRuntime.decide('repo-snapshot', 'second', baselineRules);

      const health = boundedRuntime.getRuntimeHealth();

      expect(health.telemetry.droppedEvents).toBeGreaterThan(0);
      expect(health.reasons.some((reason) => reason.includes('Telemetry dropped'))).toBe(true);
    });
  });

  describe('telemetry', () => {
    it('flushes telemetry events', () => {
      runtime.decide('repo-snapshot', 'test signal', baselineRules);

      const events = runtime.flushTelemetry();

      expect(Array.isArray(events)).toBe(true);
    });

    it('clears events after flush', () => {
      runtime.decide('repo-snapshot', 'test signal', baselineRules);

      runtime.flushTelemetry();
      const events = runtime.flushTelemetry();

      expect(events.length).toBe(0);
    });

    it('supports bounded telemetry buffer', () => {
      const telemetry = new RuntimeTelemetry({
        maxEvents: 3,
      });

      const boundedRuntime = createRuntimeIntelligence({
        telemetry,
      });

      boundedRuntime.decide('repo-snapshot', 'first', baselineRules);
      boundedRuntime.decide('repo-snapshot', 'second', baselineRules);
      boundedRuntime.decide('repo-snapshot', 'third', baselineRules);

      const snapshot = telemetry.snapshot();

      expect(snapshot.bufferedEvents).toBeLessThanOrEqual(3);
      expect(snapshot.droppedEvents).toBeGreaterThan(0);
      expect(snapshot.maxEvents).toBe(3);
    });

    it('keeps newest telemetry events when buffer is bounded', () => {
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
    });

    it('supports peeking telemetry without flushing', () => {
      runtime.decide('repo-snapshot', 'test signal', baselineRules);

      const peeked = runtime.peekTelemetry();
      const flushed = runtime.flushTelemetry();

      expect(peeked.length).toBeGreaterThan(0);
      expect(flushed.length).toBe(peeked.length);
    });

    it('ignores events when telemetry is disabled', () => {
      const telemetry = new RuntimeTelemetry({
        enabled: false,
      });

      telemetry.track({
        name: 'ignored',
        properties: {},
        timestamp: Date.now(),
        traceId: 'ignored-trace',
      });

      expect(telemetry.peek()).toHaveLength(0);
      expect(telemetry.snapshot().enabled).toBe(false);
    });

    it('survives circular telemetry properties', () => {
      const telemetry = new RuntimeTelemetry();
      const circular: Record<string, unknown> = {
        label: 'safe',
      };

      circular.self = circular;

      telemetry.track({
        name: 'circular-test',
        properties: {
          circular,
          password: 'SuperSecretPass999',
        },
        timestamp: Date.now(),
        traceId: 'circular-trace',
      });

      const serialized = JSON.stringify(telemetry.flush());

      expect(serialized).toContain('[CIRCULAR]');
      expect(serialized).toContain('[REDACTED]');
      expect(serialized).not.toContain('SuperSecretPass999');
    });
  });

  describe('withGuard()', () => {
    it('runs guarded operation successfully', async () => {
      const guard: Guard = {
        name: 'pass-guard',
        check: async (ctx) => ({
          pass: true,
          guardName: 'pass-guard',
          traceId: ctx.traceId,
          durationMs: 0,
        }),
      };

      const result = await runtime.withGuard('guarded-success', async () => 'ok', [guard]);

      expect(result.result).toBe('ok');
      expect(result.guardResults).toHaveLength(1);
      expect(result.guardResults[0].pass).toBe(true);
    });

    it('throws when guard fails', async () => {
      const guard: Guard = {
        name: 'fail-guard',
        check: async (ctx) => ({
          pass: false,
          guardName: 'fail-guard',
          reason: 'blocked',
          traceId: ctx.traceId,
          durationMs: 0,
        }),
      };

      await expect(runtime.withGuard('guarded-fail', async () => 'nope', [guard])).rejects.toThrow(
        'Guard failed',
      );
    });

    it('does not run operation when guard fails', async () => {
      let operationRan = false;

      const guard: Guard = {
        name: 'fail-before-operation',
        check: async (ctx) => ({
          pass: false,
          guardName: 'fail-before-operation',
          reason: 'blocked before operation',
          traceId: ctx.traceId,
          durationMs: 0,
        }),
      };

      await expect(
        runtime.withGuard(
          'must-not-run',
          async () => {
            operationRan = true;
            return 'bad';
          },
          [guard],
        ),
      ).rejects.toThrow('Guard failed');

      expect(operationRan).toBe(false);
    });

    it('fails closed when guard throws', async () => {
      const throwingGuard: Guard = {
        name: 'throwing-guard',
        check: async () => {
          throw new Error('guard exploded');
        },
      };

      await expect(
        runtime.withGuard('throwing-guard-operation', async () => 'nope', [throwingGuard]),
      ).rejects.toThrow('Guard failed');

      const serialized = JSON.stringify(runtime.flushTelemetry());

      expect(serialized).toContain('guard exploded');
    });

    it('fails closed on guard timeout', async () => {
      const hangingGuard: Guard = {
        name: 'hanging-guard',
        check: () =>
          new Promise<RuntimeGuardResult>(() => {
            // intentionally never resolves
          }),
      };

      await expect(
        runtime.withGuard('guard-timeout', async () => 'nope', [hangingGuard], {
          timeoutMs: 1,
        }),
      ).rejects.toThrow('Guard failed');

      const events = runtime.flushTelemetry();
      const serialized = JSON.stringify(events);

      expect(serialized).toContain('Guard timed out');
    });

    it('redacts operation error secrets from telemetry', async () => {
      await expect(
        runtime.withGuard(
          'secret-operation-error',
          async () => {
            throw new Error('authorization: Bearer abcdefghijklmnopqrstuvwxyz1234567890');
          },
          [],
        ),
      ).rejects.toThrow('authorization');

      const serialized = JSON.stringify(runtime.flushTelemetry());

      expect(serialized).not.toContain('abcdefghijklmnopqrstuvwxyz1234567890');
      expect(serialized).toContain('authorization: ****');
    });
  });

  describe('singleton instance', () => {
    it('has a singleton instance', () => {
      expect(runtimeIntelligence).toBeDefined();
      expect(runtimeIntelligence).toBeInstanceOf(RuntimeIntelligence);
    });
  });
});

describe('RuntimeTelemetry redaction', () => {
  let rules: ReturnType<typeof createBaselineContainerDecisionRules>;

  beforeEach(() => {
    rules = createBaselineContainerDecisionRules();
  });

  it('redacts GitHub tokens from telemetry events', () => {
    const runtime = createRuntimeIntelligence();

    runtime.decide('repo-snapshot', 'test signal', rules);

    const events = runtime.flushTelemetry();

    for (const event of events) {
      const eventStr = JSON.stringify(event);
      expect(eventStr).not.toMatch(/ghp_[a-zA-Z0-9]{36}/);
      expect(eventStr).not.toMatch(/gho_[a-zA-Z0-9]{36}/);
    }
  });

  it('redacts secrets from telemetry properties via withGuard error', async () => {
    const runtime = createRuntimeIntelligence();

    const guard: Guard = {
      name: 'secret-guard',
      check: async (ctx) => ({
        pass: false,
        guardName: 'secret-guard',
        reason: 'token ghp_123456789012345678901234567890123456 found in request',
        traceId: ctx.traceId,
        durationMs: 1,
      }),
    };

    await expect(runtime.withGuard('test-operation', async () => 'result', [guard])).rejects.toThrow(
      'Guard failed',
    );

    const events = runtime.flushTelemetry();
    const serialized = JSON.stringify(events);

    expect(serialized).not.toContain('ghp_123456789012345678901234567890123456');
    expect(serialized).toContain('ghp_****');
  });

  it('redacts API keys from telemetry via withGuard error', async () => {
    const runtime = createRuntimeIntelligence();

    const guard: Guard = {
      name: 'api-key-guard',
      check: async (ctx) => ({
        pass: false,
        guardName: 'api-key-guard',
        reason: 'api_key: test_api_key_1234567890abcdefghijklmnop is invalid',
        traceId: ctx.traceId,
        durationMs: 1,
      }),
    };

    await expect(runtime.withGuard('api-operation', async () => 'result', [guard])).rejects.toThrow(
      'Guard failed',
    );

    const events = runtime.flushTelemetry();
    const serialized = JSON.stringify(events);

    expect(serialized).not.toContain('test_api_key_1234567890abcdefghijklmnop');
    expect(serialized).toContain('api_key: ****');
  });

  it('redacts passwords from telemetry via withGuard error', async () => {
    const runtime = createRuntimeIntelligence();

    const guard: Guard = {
      name: 'password-guard',
      check: async (ctx) => ({
        pass: false,
        guardName: 'password-guard',
        reason: 'password: SuperSecretPass999 was rejected',
        traceId: ctx.traceId,
        durationMs: 1,
      }),
    };

    await expect(runtime.withGuard('auth-operation', async () => 'result', [guard])).rejects.toThrow(
      'Guard failed',
    );

    const events = runtime.flushTelemetry();
    const serialized = JSON.stringify(events);

    expect(serialized).not.toContain('SuperSecretPass999');
    expect(serialized).toContain('password: ****');
  });

  it('redacts GitHub fine-grained PATs', async () => {
    const runtime = createRuntimeIntelligence();

    const guard: Guard = {
      name: 'github-pat-guard',
      check: async (ctx) => ({
        pass: false,
        guardName: 'github-pat-guard',
        reason: 'github_pat_11AABBCCDD.eyJhbGciOiJIUzI1NiJ9.test_signature_here',
        traceId: ctx.traceId,
        durationMs: 1,
      }),
    };

    await expect(
      runtime.withGuard('github-operation', async () => 'result', [guard]),
    ).rejects.toThrow('Guard failed');

    const events = runtime.flushTelemetry();
    const serialized = JSON.stringify(events);

    expect(serialized).not.toContain('github_pat_11AABBCCDD');
    expect(serialized).toContain('github_pat_****');
  });

  it('redacts Gemini API keys', async () => {
    const runtime = createRuntimeIntelligence();

    const guard: Guard = {
      name: 'gemini-guard',
      check: async (ctx) => ({
        pass: false,
        guardName: 'gemini-guard',
        reason: 'Gemini key AIzaSyBabcdefghijk1234567890abcdefgh is invalid',
        traceId: ctx.traceId,
        durationMs: 1,
      }),
    };

    await expect(
      runtime.withGuard('gemini-operation', async () => 'result', [guard]),
    ).rejects.toThrow('Guard failed');

    const events = runtime.flushTelemetry();
    const serialized = JSON.stringify(events);

    expect(serialized).not.toContain('AIzaSyBabcdefghijk1234567890abcdefgh');
    expect(serialized).toContain('AIza****');
  });

  it('redacts OpenAI keys', async () => {
    const runtime = createRuntimeIntelligence();

    const guard: Guard = {
      name: 'openai-guard',
      check: async (ctx) => ({
        pass: false,
        guardName: 'openai-guard',
        reason: 'OpenAI key sk-proj-abcdefghijklmnopqrstuvwxyz1234567890 is invalid',
        traceId: ctx.traceId,
        durationMs: 1,
      }),
    };

    await expect(
      runtime.withGuard('openai-operation', async () => 'result', [guard]),
    ).rejects.toThrow('Guard failed');

    const events = runtime.flushTelemetry();
    const serialized = JSON.stringify(events);

    expect(serialized).not.toContain('sk-proj-abcdefghijklmnopqrstuvwxyz1234567890');
    expect(serialized).toContain('sk-****');
  });

  it('redacts authorization headers and bearer tokens', async () => {
    const runtime = createRuntimeIntelligence();

    const guard: Guard = {
      name: 'bearer-guard',
      check: async (ctx) => ({
        pass: false,
        guardName: 'bearer-guard',
        reason: 'authorization: Bearer abcdefghijklmnopqrstuvwxyz1234567890',
        traceId: ctx.traceId,
        durationMs: 1,
      }),
    };

    await expect(runtime.withGuard('bearer-operation', async () => 'result', [guard])).rejects.toThrow(
      'Guard failed',
    );

    const serialized = JSON.stringify(runtime.flushTelemetry());

    expect(serialized).not.toContain('abcdefghijklmnopqrstuvwxyz1234567890');
    expect(serialized).toContain('authorization: ****');
  });

  it('redacts nested sensitive key names even when values do not match token regexes', () => {
    const telemetry = new RuntimeTelemetry();

    telemetry.track({
      name: 'nested-secret-test',
      properties: {
        nested: {
          apiKey: 'plain-but-sensitive-value',
          credential: 'credential-value',
          safe: 'visible',
        },
      },
      timestamp: Date.now(),
      traceId: 'nested-trace',
    });

    const serialized = JSON.stringify(telemetry.flush());

    expect(serialized).toContain('visible');
    expect(serialized).toContain('[REDACTED]');
    expect(serialized).not.toContain('plain-but-sensitive-value');
    expect(serialized).not.toContain('credential-value');
  });
});

describe('RuntimeCircuitBreaker', () => {
  it('starts in closed state', () => {
    const cb = new RuntimeCircuitBreaker();

    expect(cb.getState()).toBe('closed');
    expect(cb.getFailureCount()).toBe(0);
  });

  it('opens after threshold failures', async () => {
    const cb = new RuntimeCircuitBreaker(3, 30000, 'test');

    for (let i = 0; i < 3; i += 1) {
      await expect(
        cb.call(async () => {
          throw new Error('fail');
        }),
      ).rejects.toThrow('fail');
    }

    expect(cb.getState()).toBe('open');
    expect(cb.getFailureCount()).toBe(3);
  });

  it('allows calls in closed state', async () => {
    const cb = new RuntimeCircuitBreaker(3, 30000, 'test');

    const result = await cb.call(async () => 'success');

    expect(result).toBe('success');
    expect(cb.getState()).toBe('closed');
  });

  it('rejects calls when open', async () => {
    const cb = new RuntimeCircuitBreaker(1, 30000, 'test');

    await expect(
      cb.call(async () => {
        throw new Error('fail');
      }),
    ).rejects.toThrow('fail');

    await expect(cb.call(async () => 'should not reach')).rejects.toThrow(
      'Circuit breaker open',
    );
  });

  it('allows a half-open probe after timeout and closes on success', async () => {
    const cb = new RuntimeCircuitBreaker(1, 1, 'half-open-test');

    await expect(
      cb.call(async () => {
        throw new Error('fail');
      }),
    ).rejects.toThrow('fail');

    expect(cb.getState()).toBe('open');

    await new Promise((resolve) => setTimeout(resolve, 5));

    const result = await cb.call(async () => 'recovered');

    expect(result).toBe('recovered');
    expect(cb.getState()).toBe('closed');
    expect(cb.getFailureCount()).toBe(0);
  });

  it('reopens when half-open probe fails', async () => {
    const cb = new RuntimeCircuitBreaker(1, 1, 'half-open-fail-test');

    await expect(
      cb.call(async () => {
        throw new Error('initial fail');
      }),
    ).rejects.toThrow('initial fail');

    await new Promise((resolve) => setTimeout(resolve, 5));

    await expect(
      cb.call(async () => {
        throw new Error('probe fail');
      }),
    ).rejects.toThrow('probe fail');

    expect(cb.getState()).toBe('open');
  });

  it('returns snapshot and supports reset', async () => {
    const cb = new RuntimeCircuitBreaker(1, 30000, 'snapshot-reset-test');

    await expect(
      cb.call(async () => {
        throw new Error('fail');
      }),
    ).rejects.toThrow('fail');

    const openSnapshot = cb.snapshot();

    expect(openSnapshot.name).toBe('snapshot-reset-test');
    expect(openSnapshot.state).toBe('open');
    expect(openSnapshot.failures).toBe(1);
    expect(openSnapshot.threshold).toBe(1);

    cb.reset();

    const resetSnapshot = cb.snapshot();

    expect(resetSnapshot.state).toBe('closed');
    expect(resetSnapshot.failures).toBe(0);
    expect(resetSnapshot.halfOpenProbeInFlight).toBe(false);
  });

  it('does not run operation while open', async () => {
    const cb = new RuntimeCircuitBreaker(1, 30000, 'open-no-run-test');
    let operationRan = false;

    await expect(
      cb.call(async () => {
        throw new Error('open now');
      }),
    ).rejects.toThrow('open now');

    await expect(
      cb.call(async () => {
        operationRan = true;
        return 'bad';
      }),
    ).rejects.toThrow('Circuit breaker open');

    expect(operationRan).toBe(false);
  });
});

describe('runGuardChain', () => {
  const mockGuard: Guard = {
    name: 'test-guard',
    check: async (ctx) => ({
      pass: true,
      guardName: 'test-guard',
      traceId: ctx.traceId,
      durationMs: 1,
    }),
  };

  const failingGuard: Guard = {
    name: 'failing-guard',
    check: async (ctx) => ({
      pass: false,
      guardName: 'failing-guard',
      reason: 'Test failure',
      traceId: ctx.traceId,
      durationMs: 1,
    }),
  };

  it('runs all guards in chain', async () => {
    const ctx: RuntimeContext = {
      traceId: 'test-trace',
      timestamp: Date.now(),
    };

    const result = await runGuardChain(ctx, {
      preFlight: [mockGuard],
      main: [mockGuard],
      postFlight: [mockGuard],
    });

    expect(result.pass).toBe(true);
    expect(result.results.length).toBe(3);
  });

  it('stops on first failing guard by default', async () => {
    const ctx: RuntimeContext = {
      traceId: 'test-trace',
      timestamp: Date.now(),
    };

    const result = await runGuardChain(ctx, {
      preFlight: [mockGuard, failingGuard, mockGuard],
      main: [],
      postFlight: [],
    });

    expect(result.pass).toBe(false);
    expect(result.results.length).toBe(2);
  });

  it('can continue after failing guard when failFast is false', async () => {
    const ctx: RuntimeContext = {
      traceId: 'test-trace',
      timestamp: Date.now(),
    };

    const result = await runGuardChain(ctx, {
      preFlight: [mockGuard, failingGuard, mockGuard],
      main: [],
      postFlight: [],
      failFast: false,
    });

    expect(result.pass).toBe(false);
    expect(result.results.length).toBe(3);
  });

  it('fails closed when a guard throws', async () => {
    const ctx: RuntimeContext = {
      traceId: 'throw-trace',
      timestamp: Date.now(),
    };

    const throwingGuard: Guard = {
      name: 'throwing-guard',
      check: async () => {
        throw new Error('guard throw');
      },
    };

    const result = await runGuardChain(ctx, {
      preFlight: [throwingGuard],
      main: [],
      postFlight: [],
    });

    expect(result.pass).toBe(false);
    expect(result.results).toHaveLength(1);
    expect(result.results[0].reason).toContain('guard throw');
  });

  it('fails closed when a guard times out', async () => {
    const ctx: RuntimeContext = {
      traceId: 'timeout-trace',
      timestamp: Date.now(),
    };

    const hangingGuard: Guard = {
      name: 'hanging-guard',
      check: () =>
        new Promise<RuntimeGuardResult>(() => {
          // intentionally never resolves
        }),
    };

    const result = await runGuardChain(ctx, {
      preFlight: [hangingGuard],
      main: [],
      postFlight: [],
      timeoutMs: 1,
    });

    expect(result.pass).toBe(false);
    expect(result.results.length).toBe(1);
    expect(result.results[0].guardName).toBe('hanging-guard');
    expect(result.results[0].reason).toContain('Guard timed out');
  });
});
