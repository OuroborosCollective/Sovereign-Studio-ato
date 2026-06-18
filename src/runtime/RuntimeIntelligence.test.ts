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
  type RuntimeContext,
  type Guard,
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

  // Note: FullPipelineBridge requires all 7 bridge properties
  // Integration test skipped - needs complete bridge setup
  describe.skip('validatePipeline()', () => {
    it('validates full pipeline bridge', () => {
      // TODO: Create complete bridge for integration test
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
