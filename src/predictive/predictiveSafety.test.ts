import { describe, expect, it } from 'vitest';
import type { PredictiveLayerSnapshot } from './types';
import { checkActionSafety, getSystemSafetyStatus, predictiveGuardPreFlight } from './predictiveSafety';

function snapshot(overrides: Partial<PredictiveLayerSnapshot> = {}): PredictiveLayerSnapshot {
  return {
    active: true,
    phase: 'idle',
    nodeCount: 4,
    synapseCount: 3,
    patternCount: 2,
    avgConfidence: 0.82,
    errorRate: 0.02,
    memoryUsageBytes: 512,
    timestamp: 1_700_000_000_000,
    ...overrides,
  };
}

describe('predictiveSafety', () => {
  it('does not report no-data predictive state as proven safe', () => {
    const check = checkActionSafety(null, 'publish', 'runtime.container.publish');

    expect(check.safety).toBe('warning');
    expect(check.confidence).toBe(0);
    expect(check.recommendation).toBe('caution');
    expect(check.reason).toContain('not proof of safety');
  });

  it('returns non-blocking advisory clear only when evidence is healthy', () => {
    const check = checkActionSafety(snapshot(), 'build', 'runtime.container.build');

    expect(check.safety).toBe('safe');
    expect(check.recommendation).toBe('proceed');
    expect(check.reason).toContain('hard runtime guards');
  });

  it('blocks when predictive confidence is very low', () => {
    const check = checkActionSafety(snapshot({ avgConfidence: 0.1 }), 'publish', 'runtime.container.publish');

    expect(check.safety).toBe('critical');
    expect(check.recommendation).toBe('block');
  });

  it('blocks when error rate is dangerous', () => {
    const check = checkActionSafety(snapshot({ errorRate: 0.4 }), 'publish', 'runtime.container.publish');

    expect(check.safety).toBe('critical');
    expect(check.similarFailures.length).toBeGreaterThan(0);
    expect(check.recommendation).toBe('block');
  });

  it('keeps system health neutral when predictive layer has no evidence', () => {
    const health = getSystemSafetyStatus(null);

    expect(health.status).toBe('warning');
    expect(health.isHealthy).toBe(true);
    expect(health.message).toContain('neutral advisory');
  });

  it('preflight fails closed only for unhealthy predictive evidence', async () => {
    const result = await predictiveGuardPreFlight(snapshot({ errorRate: 0.5 }), { operation: 'publish' });

    expect(result.pass).toBe(false);
    expect(result.reason).toContain('Critical predictive signal');
  });
});
