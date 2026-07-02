import { describe, expect, it } from 'vitest';

import type { RuntimeContext } from '../runtime/RuntimeIntelligence';
import type { PredictiveLayerSnapshot } from './types';
import {
  createBuildPredictiveGuard,
  createPredictiveGuardChain,
  createPublishPredictiveGuard,
  createSystemHealthPredictiveGuard,
} from './runtimeIntelligenceIntegration';

function runtimeContext(traceId = 'predictive-trace-1'): RuntimeContext {
  return {
    traceId,
    timestamp: 1,
    containerId: 'builder',
    operationId: 'predictive-test',
  };
}

function snapshot(overrides: Partial<PredictiveLayerSnapshot> = {}): PredictiveLayerSnapshot {
  return {
    active: true,
    phase: 'active',
    nodeCount: 4,
    synapseCount: 6,
    patternCount: 3,
    avgConfidence: 0.82,
    errorRate: 0.02,
    memoryUsageBytes: 1024,
    timestamp: 1,
    ...overrides,
  };
}

describe('predictive RuntimeIntelligence integration', () => {
  it('keeps build guard advisory and trace-bound when predictive evidence is missing', async () => {
    const guard = createBuildPredictiveGuard(() => null);
    const result = await guard.check(runtimeContext('trace-build'));

    expect(result.pass).toBe(true);
    expect(result.guardName).toBe('predictive_build_guard');
    expect(result.traceId).toBe('trace-build');
    expect(result.reason).toContain('Predictive layer has no runtime evidence yet');
    expect(result.properties?.warnOnly).toBe(true);
  });

  it('blocks publish guard when predictive confidence is below the hard threshold', async () => {
    const guard = createPublishPredictiveGuard(() => snapshot({ avgConfidence: 0.22, errorRate: 0.05 }));
    const result = await guard.check(runtimeContext('trace-publish'));

    expect(result.pass).toBe(false);
    expect(result.guardName).toBe('predictive_publish_guard');
    expect(result.traceId).toBe('trace-publish');
    expect(result.properties?.confidence).toBe(0.22);
    expect(result.properties?.warnOnly).toBe(false);
    expect(result.reason).toContain('Action: publish');
  });

  it('fails system health guard on critical predictive error rate', async () => {
    const guard = createSystemHealthPredictiveGuard(() => snapshot({ avgConfidence: 0.9, errorRate: 0.5 }));
    const result = await guard.check(runtimeContext('trace-health'));

    expect(result.pass).toBe(false);
    expect(result.guardName).toBe('predictive_system_health_guard');
    expect(result.traceId).toBe('trace-health');
    expect(result.reason).toContain('System health');
    expect(result.properties?.healthStatus).toBe('critical');
    expect(result.properties?.errorRate).toBe(0.5);
  });

  it('creates a guard chain wired for preflight, build and publish checks', () => {
    const chain = createPredictiveGuardChain(() => snapshot());

    expect(chain.preFlight.map((guard) => guard.name)).toEqual([
      'predictive_system_health_guard',
    ]);
    expect(chain.main.map((guard) => guard.name)).toEqual([
      'predictive_build_guard',
      'predictive_publish_guard',
    ]);
    expect(chain.postFlight).toEqual([]);
  });
});
