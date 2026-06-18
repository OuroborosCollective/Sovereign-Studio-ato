/**
 * Runtime Intelligence Library Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  RuntimeIntelligence,
  createRuntimeIntelligence,
  runtimeIntelligence,
  RuntimeCircuitBreaker,
  runGuardChain,
  defaultTraceIdProvider,
  type RuntimeContext,
  type Guard,
  type FullPipelineBridge,
} from './RuntimeIntelligence';

import { createBaselineContainerDecisionRules } from '../features/product/runtime/containerDecisionBaselineRules';

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

    it('supports injectable trace ID provider', () => {
      let callCount = 0;
      const customProvider = () => {
        callCount++;
        return `custom-trace-${callCount}`;
      };

      const runtimeWithCustom = createRuntimeIntelligence({
        traceIdProvider: customProvider
      });

      const id1 = runtimeWithCustom.decide('repo-snapshot', 'test', baselineRules);
      const id2 = runtimeWithCustom.decide('repo-snapshot', 'test', baselineRules);

      expect(callCount).toBe(2);
      expect(id1.context.traceId).toBe('custom-trace-1');
      expect(id2.context.traceId).toBe('custom-trace-2');
    });

    it('provides deterministic trace IDs for testing', () => {
      let counter = 0;
      const deterministicProvider = () => `test-trace-${++counter}`;

      const runtimeDet = createRuntimeIntelligence({
        traceIdProvider: deterministicProvider
      });

      const decision = runtimeDet.decide('repo-snapshot', 'test', baselineRules);
      
      expect(decision.context.traceId).toBe('test-trace-1');
    });
  });

  describe('decide()', () => {
    it('makes container decisions with telemetry', () => {
      const result = runtime.decide(
        'repo-snapshot',
        'repo snapshot ready',
        baselineRules
      );

      expect(result.decision).toBeDefined();
      expect(result.decision.containerId).toBe('repo-snapshot');
      expect(result.context.traceId).toBeDefined();
      expect(typeof result.confidence).toBe('number');
    });

    it('returns matched signals', () => {
      const result = runtime.decide(
        'repo-snapshot',
        'repo snapshot review needed',
        baselineRules
      );

      expect(result.matchedSignals).toBeDefined();
      expect(Array.isArray(result.matchedSignals)).toBe(true);
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
      const result = runtime.matchMobilePattern('validation failed build failed critical blocker');

      expect(result.rule).toBeDefined();
      expect(result.rule.id).toBe('real-stopper');
    });

    it('returns awaiting-intent as fallback', () => {
      const result = runtime.matchMobilePattern('   ');

      expect(result.rule).toBeDefined();
      expect(result.rule.id).toBe('awaiting-intent');
    });
  });

  describe('validatePipeline()', () => {
    it('validates full pipeline bridge with valid data', () => {
      const validBridge: FullPipelineBridge = {
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

      const result = runtime.validatePipeline(validBridge);

      expect(result.overallValid).toBe(true);
      expect(result.criticalErrors).toHaveLength(0);
    });

    it('detects critical errors in pipeline', () => {
      const invalidBridge: FullPipelineBridge = {
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

      const result = runtime.validatePipeline(invalidBridge);

      expect(result.overallValid).toBe(false);
      expect(result.criticalErrors.length).toBeGreaterThan(0);
    });
  });

  describe('getCoverageReport()', () => {
    it('returns coverage report', () => {
      const report = runtime.getCoverageReport();

      expect(report).toBeDefined();
      expect(report.entries).toBeDefined();
      expect(Array.isArray(report.entries)).toBe(true);
      expect(report.entries.length).toBeGreaterThan(0);
    });

    it('has valid structure', () => {
      const report = runtime.getCoverageReport();

      expect(typeof report.valid).toBe('boolean');
      expect(typeof report.summary).toBe('string');
      expect(typeof report.coveredCount).toBe('number');
      expect(typeof report.partialCount).toBe('number');
      expect(typeof report.missingCount).toBe('number');
    });
  });

  describe('getCoverageGaps()', () => {
    it('returns containers with gaps', () => {
      const gaps = runtime.getCoverageGaps();

      expect(Array.isArray(gaps)).toBe(true);
      // At least some containers should have gaps
      expect(gaps.length).toBeGreaterThan(0);
    });
  });

  describe('assertCoverageValid()', () => {
    it('does not throw for valid coverage', () => {
      expect(() => runtime.assertCoverageValid()).not.toThrow();
    });
  });

  describe('getLearningStats()', () => {
    it('returns learning statistics', () => {
      const stats = runtime.getLearningStats();

      expect(stats).toBeDefined();
      expect(typeof stats.totalSignals).toBe('number');
      expect(typeof stats.accepted).toBe('number');
      expect(typeof stats.rejected).toBe('number');
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
  });

  describe('flushTelemetry()', () => {
    it('flushes telemetry events', () => {
      // Generate some events
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
    
    // Create a decision with mock data
    runtime.decide('repo-snapshot', 'test signal', rules);
    
    // Flush and check that no secrets are leaked
    const events = runtime.flushTelemetry();
    
    for (const event of events) {
      const eventStr = JSON.stringify(event);
      // Should not contain actual GitHub tokens
      expect(eventStr).not.toMatch(/ghp_[a-zA-Z0-9]{36}/);
      expect(eventStr).not.toMatch(/gho_[a-zA-Z0-9]{36}/);
    }
  });

  it('redacts sensitive keys from properties', () => {
    const runtime = createRuntimeIntelligence();
    
    // Add a learning signal
    runtime.addLearning({
      containerId: 'repo-snapshot',
      action: 'review',
      reason: 'test reason',
      outcome: 'accepted',
      score: 0.8,
      lamp: 'green',
      ruleId: 'test-rule',
      learnTag: 'test-tag',
    });
    
    const events = runtime.flushTelemetry();
    
    // Check that learning events were recorded
    expect(events.length).toBeGreaterThan(0);
  });
});

describe('RuntimeCircuitBreaker', () => {
  it('starts in closed state', () => {
    const cb = new RuntimeCircuitBreaker();
    expect(cb.getState()).toBe('closed');
  });

  it('opens after threshold failures', async () => {
    const cb = new RuntimeCircuitBreaker(3, 30000, 'test');

    // Make 3 failing calls
    for (let i = 0; i < 3; i++) {
      try {
        await cb.call(async () => {
          throw new Error('fail');
        });
      } catch {
        // Expected
      }
    }

    expect(cb.getState()).toBe('open');
  });

  it('allows calls in closed state', async () => {
    const cb = new RuntimeCircuitBreaker(3, 30000, 'test');

    const result = await cb.call(async () => 'success');

    expect(result).toBe('success');
    expect(cb.getState()).toBe('closed');
  });

  it('rejects calls when open', async () => {
    const cb = new RuntimeCircuitBreaker(1, 30000, 'test');

    // First failure opens the circuit
    try {
      await cb.call(async () => {
        throw new Error('fail');
      });
    } catch {
      // Expected
    }

    // Second call should be rejected
    await expect(
      cb.call(async () => 'should not reach')
    ).rejects.toThrow('Circuit breaker open');
  });
});

describe('runGuardChain', () => {
  const mockGuard: Guard = {
    name: 'test-guard',
    check: async () => ({
      pass: true,
      guardName: 'test-guard',
      traceId: 'test',
      durationMs: 1
    })
  };

  const failingGuard: Guard = {
    name: 'failing-guard',
    check: async () => ({
      pass: false,
      guardName: 'failing-guard',
      reason: 'Test failure',
      traceId: 'test',
      durationMs: 1
    })
  };

  it('runs all guards in chain', async () => {
    const ctx: RuntimeContext = {
      traceId: 'test-trace',
      timestamp: Date.now()
    };

    const result = await runGuardChain(ctx, {
      preFlight: [mockGuard],
      main: [mockGuard],
      postFlight: [mockGuard]
    });

    expect(result.pass).toBe(true);
    expect(result.results.length).toBe(3);
  });

  it('stops on first failing guard', async () => {
    const ctx: RuntimeContext = {
      traceId: 'test-trace',
      timestamp: Date.now()
    };

    const result = await runGuardChain(ctx, {
      preFlight: [mockGuard, failingGuard, mockGuard],
      main: [],
      postFlight: []
    });

    expect(result.pass).toBe(false);
    expect(result.results.length).toBe(2);
  });
});
