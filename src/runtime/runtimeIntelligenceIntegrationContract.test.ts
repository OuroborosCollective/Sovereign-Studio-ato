import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

function source(path: string): string {
  return readFileSync(join(process.cwd(), path), 'utf8');
}

describe('Runtime Intelligence integration contract', () => {
  it('keeps the stable runtime barrel connected to core intelligence and repo snapshots', () => {
    const text = source('src/runtime/index.ts');

    expect(text).toContain("from './RuntimeIntelligence'");
    expect(text).toContain("from './repoSnapshotRuntime'");
    expect(text).toContain('export const runtimeIntelligence');
    expect(text).toContain('attachRepoSnapshotRuntime(baseRuntimeIntelligence)');
  });

  it('keeps ChatRuntime connected to validation, telemetry and model-health gates', () => {
    const text = source('src/features/product/runtime/chatRuntime.ts');

    expect(text).toContain("from '../../../runtime/RuntimeIntelligence'");
    expect(text).toContain('globalTelemetry.track');
    expect(text).toContain('runtimeIntelligence.getModelHealthReport()');
    expect(text).toContain('runtimeIntelligence.getModelHealthFallbackResult()');
    expect(text).toContain('runtimeIntelligence.recordModelSuccessForFallback');
    expect(text).toContain('runtimeIntelligence.recordModelFailureForFallback');
  });

  it('keeps model-health hook routed through RuntimeIntelligence rather than local UI truth', () => {
    const text = source('src/features/product/hooks/useRuntimeModelHealth.ts');

    expect(text).toContain("from '../../../runtime/RuntimeIntelligence'");
    expect(text).toContain('runtimeIntelligence.setModelHealthAdapters');
    expect(text).toContain('runtimeIntelligence.startModelHealthMonitoring');
    expect(text).toContain('runtimeIntelligence.stopModelHealthMonitoring');
    expect(text).toContain('runtimeIntelligence.checkModelHealth');
    expect(text).toContain('runtimeIntelligence.assertModelHealthReady');
  });

  it('keeps predictive guards on the RuntimeGuardResult contract', () => {
    const text = source('src/predictive/runtimeIntelligenceIntegration.ts');

    expect(text).toContain("from '../runtime/RuntimeIntelligence'");
    expect(text).toContain('createPredictiveRuntimeGuard');
    expect(text).toContain('createSystemHealthPredictiveGuard');
    expect(text).toContain('createPredictiveGuardChainForAction');
    expect(text).toContain('createPredictiveGuardChain');
    expect(text).toContain('checkActionSafety(snapshot, action, nodeId)');
    expect(text).toContain('getSystemSafetyStatus(snapshot)');
  });

  it('binds the product RuntimeIntelligence singleton to the same predictive layer as runtime bridges', () => {
    const runtimeText = source('src/runtime/RuntimeIntelligence.ts');
    const sessionBridgeText = source('src/features/product/runtime/sovereignSessionIntelligenceBridge.ts');
    const areBridgeText = source('src/features/inference/arePredictiveBridge.ts');

    expect(runtimeText).toContain('predictiveLayer?: PredictiveLayer');
    expect(runtimeText).toContain('predictiveLayer: getDefaultPredictiveLayer()');
    expect(sessionBridgeText).toContain('getDefaultPredictiveLayer');
    expect(areBridgeText).toContain('getDefaultPredictiveLayer');
  });
});
