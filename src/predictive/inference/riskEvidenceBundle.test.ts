import { describe, expect, it } from 'vitest';
import { createModelReceipt } from './modelReceipt';
import {
  applyCausalVerdict,
  createRiskEvidenceBundle,
  determineCausalVerdict,
  validateRiskBundle,
} from './riskEvidenceBundle';
import { computeReceiptHash, type ModelReceipt } from './types';

const runtimeRevision = 'a'.repeat(40);
const digest = 'b'.repeat(64);

function makeReceipt(overrides: Partial<ModelReceipt> = {}): ModelReceipt {
  const receipt = createModelReceipt({
    channelType: 'hard_invariant',
    modelClass: 'hard_invariant_deterministic',
    implementationVersion: '1.0.0',
    revisionBinding: {
      runtimeRevision,
      configRevision: 'config-v1',
      schemaVersion: '1.0',
      boundAt: Date.now(),
    },
    featureSchemaHash: digest,
    inputWindowHash: {
      hash: digest,
      featureHash: digest,
      signalCount: 1,
      windowStart: Date.now() - 1000,
      windowEnd: Date.now(),
    },
    modelStateHash: {
      parametersHash: digest,
      weightsHash: digest,
      configHash: digest,
      libraryVersion: '1.0.0',
    },
    score: 1,
    calibrationMetadata: {
      method: 'deterministic',
      score: 1,
      sampleSize: 1,
    },
  });
  const updated = { ...receipt, ...overrides };
  return {
    ...updated,
    receiptHash: computeReceiptHash(updated),
  };
}

function makeBundle(receipts = [makeReceipt()]) {
  return createRiskEvidenceBundle({
    channelReceipts: receipts,
    traceId: 'trace-1',
    currentRevision: runtimeRevision,
    preActionWindow: {
      startTimestamp: Date.now() - 1000,
      endTimestamp: Date.now(),
      signalCount: 1,
    },
  });
}

describe('predictive risk evidence bundle', () => {
  it('creates and validates a canonical SHA-256-bound bundle', () => {
    const bundle = makeBundle();
    const validation = validateRiskBundle(bundle, runtimeRevision);

    expect(bundle.bundleHash).toMatch(/^[0-9a-f]{64}$/);
    expect(validation.isValid).toBe(true);
    expect(validation.errors).toHaveLength(0);
  });

  it('rejects empty, stale, and revision-mismatched receipt sets', () => {
    expect(() => makeBundle([])).toThrow(TypeError);

    const stale = makeReceipt({ createdAt: Date.now() - 10 * 60 * 1000 });
    expect(() => makeBundle([stale])).toThrow(TypeError);

    const mismatched = makeReceipt({
      revisionBinding: {
        runtimeRevision: 'c'.repeat(40),
        configRevision: 'config-v1',
        schemaVersion: '1.0',
        boundAt: Date.now(),
      },
    });
    expect(() => makeBundle([mismatched])).toThrow(TypeError);
  });

  it('detects tampering in a receipt and in bundle metadata', () => {
    const bundle = makeBundle();
    const tamperedReceiptBundle = {
      ...bundle,
      channelReceipts: [{ ...bundle.channelReceipts[0], score: 0 }],
    };
    expect(validateRiskBundle(tamperedReceiptBundle, runtimeRevision).isValid).toBe(false);

    const tamperedMetadataBundle = { ...bundle, traceId: 'other-trace' };
    expect(validateRiskBundle(tamperedMetadataBundle, runtimeRevision).errors).toContain(
      'Bundle hash mismatch',
    );
  });

  it('binds post-action readback to the exact bundle and refreshes its hash', () => {
    const bundle = makeBundle();
    const verification = {
      bundleId: bundle.bundleId,
      startTimestamp: Date.now(),
      endTimestamp: Date.now() + 1000,
      observedEffects: [{ effect: 'cpu decreased', observed: true }],
      externalChangesDetected: false,
    };
    const updated = applyCausalVerdict(bundle, verification);

    expect(updated.postActionWindow?.verdict).toBe('EFFECT_VERIFIED');
    expect(updated.bundleHash).not.toBe(bundle.bundleHash);
    expect(validateRiskBundle(updated, runtimeRevision).isValid).toBe(true);

    expect(determineCausalVerdict(
      { ...verification, bundleId: 'wrong-bundle' },
      bundle,
    ).verdict).toBe('EFFECT_CONTRADICTED');
  });
});
