/**
 * Predictive Layer Schemas - Validation Tests
 */

import { describe, it, expect } from 'vitest';
import {
  SCHEMA_VERSIONS,
  validateRuntimeSignal,
  isValidRuntimeSignal,
  validatePredictionResult,
  isValidPredictionResult,
  validatePredictionError,
  isValidPredictionError,
  validateBoundedActionPlan,
  isValidBoundedActionPlan,
  validateRuntimeActionReceipt,
  isValidRuntimeActionReceipt,
  validatePredictiveSnapshot,
  isValidPredictiveSnapshot,
  validateRuntimeReadback,
  isValidRuntimeReadback,
  validateRiskEvidenceBundle,
  isValidRiskEvidenceBundle,
} from './schemas';

describe('Schema Version Constants', () => {
  it('should have all required schema versions', () => {
    expect(SCHEMA_VERSIONS.RUNTIME_SIGNAL).toBe('runtime-signal.v1');
    expect(SCHEMA_VERSIONS.PREDICTION_RESULT).toBe('prediction-result.v1');
    expect(SCHEMA_VERSIONS.PREDICTION_ERROR).toBe('prediction-error.v1');
    expect(SCHEMA_VERSIONS.RUNTIME_ACTION_RECEIPT).toBe('runtime-action-receipt.v1');
    expect(SCHEMA_VERSIONS.BOUNDED_ACTION_PLAN).toBe('bounded-action-plan.v1');
    expect(SCHEMA_VERSIONS.PREDICTIVE_SNAPSHOT).toBe('predictive-snapshot.v1');
    expect(SCHEMA_VERSIONS.RUNTIME_READBACK).toBe('runtime-readback.v1');
    expect(SCHEMA_VERSIONS.RISK_EVIDENCE_BUNDLE).toBe('risk-evidence-bundle.v1');
  });
});

describe('Runtime Signal Schema', () => {
  describe('validateRuntimeSignal', () => {
    it('should validate a complete valid signal', () => {
      const signal = {
        schemaVersion: 'runtime-signal.v1',
        id: 'sig-123',
        node: 'runtime.decision',
        value: 0.85,
        timestamp: Date.now(),
        traceId: 'trace-456',
        sourceRevision: 'a'.repeat(40),
        signalHash: 'b'.repeat(64),
      };
      const result = validateRuntimeSignal(signal);
      expect(result.id).toBe('sig-123');
      expect(result.node).toBe('runtime.decision');
      expect(result.schemaVersion).toBe('runtime-signal.v1');
    });

    it('should validate a minimal valid signal', () => {
      const signal = {
        id: 'sig-minimal',
        node: 'test.node',
        value: 0,
        timestamp: Date.now(),
        traceId: 'trace-minimal',
      };
      const result = validateRuntimeSignal(signal);
      expect(result.id).toBe('sig-minimal');
    });

    it('should throw for null input', () => {
      expect(() => validateRuntimeSignal(null)).toThrow(TypeError);
    });

    it('should throw for non-object input', () => {
      expect(() => validateRuntimeSignal('string')).toThrow(TypeError);
    });

    it('should throw for missing required fields', () => {
      expect(() => validateRuntimeSignal({ id: 'test' })).toThrow();
    });

    it('should throw for invalid timestamp', () => {
      expect(() =>
        validateRuntimeSignal({
          id: 'sig-123',
          node: 'test',
          value: 0,
          timestamp: 123, // too old
          traceId: 'trace',
        })
      ).toThrow(RangeError);
    });

    it('should throw for empty id', () => {
      expect(() =>
        validateRuntimeSignal({
          id: '',
          node: 'test',
          value: 0,
          timestamp: Date.now(),
          traceId: 'trace',
        })
      ).toThrow(RangeError);
    });

    it('should throw for invalid Git SHA in sourceRevision', () => {
      expect(() =>
        validateRuntimeSignal({
          id: 'sig-123',
          node: 'test',
          value: 0,
          timestamp: Date.now(),
          traceId: 'trace',
          sourceRevision: 'not-a-sha',
        })
      ).toThrow(RangeError);
    });

    it('should throw for invalid SHA-256 in signalHash', () => {
      expect(() =>
        validateRuntimeSignal({
          id: 'sig-123',
          node: 'test',
          value: 0,
          timestamp: Date.now(),
          traceId: 'trace',
          signalHash: 'not-a-sha256',
        })
      ).toThrow(RangeError);
    });
  });

  describe('isValidRuntimeSignal', () => {
    it('should return true for valid signal', () => {
      const signal = {
        id: 'sig-valid',
        node: 'runtime.test',
        value: 0.5,
        timestamp: Date.now(),
        traceId: 'trace-valid',
      };
      expect(isValidRuntimeSignal(signal)).toBe(true);
    });

    it('should return false for invalid signal', () => {
      expect(isValidRuntimeSignal(null)).toBe(false);
      expect(isValidRuntimeSignal({})).toBe(false);
      expect(isValidRuntimeSignal({ id: '' })).toBe(false);
    });
  });
});

describe('Prediction Result Schema', () => {
  describe('validatePredictionResult', () => {
    it('should validate a complete valid prediction', () => {
      const prediction = {
        schemaVersion: 'prediction-result.v1',
        id: 'pred-123',
        predictedValue: 0.75,
        confidence: 0.85,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        sourceRevision: 'a'.repeat(40),
        patternId: 'pattern-789',
        embedding: [0.1, 0.2, 0.3],
      };
      const result = validatePredictionResult(prediction);
      expect(result.id).toBe('pred-123');
      expect(result.confidence).toBe(0.85);
      expect(result.patternId).toBe('pattern-789');
    });

    it('should throw for confidence > 1', () => {
      expect(() =>
        validatePredictionResult({
          id: 'pred-123',
          predictedValue: 0.75,
          confidence: 1.5,
          node: 'test',
          timestamp: Date.now(),
          traceId: 'trace',
        })
      ).toThrow(RangeError);
    });

    it('should throw for negative confidence', () => {
      expect(() =>
        validatePredictionResult({
          id: 'pred-123',
          predictedValue: 0.75,
          confidence: -0.1,
          node: 'test',
          timestamp: Date.now(),
          traceId: 'trace',
        })
      ).toThrow(RangeError);
    });

    it('should validate embedding dimensions', () => {
      const prediction = {
        id: 'pred-embed',
        predictedValue: 0.5,
        confidence: 0.8,
        node: 'test',
        timestamp: Date.now(),
        traceId: 'trace',
        embedding: [1, 2, 3],
      };
      const result = validatePredictionResult(prediction);
      expect(result.embedding).toEqual([1, 2, 3]);
    });
  });

  describe('isValidPredictionResult', () => {
    it('should return true for valid prediction', () => {
      const prediction = {
        id: 'pred-valid',
        predictedValue: 0.5,
        confidence: 0.8,
        node: 'runtime.test',
        timestamp: Date.now(),
        traceId: 'trace-valid',
      };
      expect(isValidPredictionResult(prediction)).toBe(true);
    });

    it('should return false for invalid prediction', () => {
      expect(isValidPredictionResult(null)).toBe(false);
      expect(isValidPredictionResult({ id: 'test' })).toBe(false);
    });
  });
});

describe('Prediction Error Schema', () => {
  describe('validatePredictionError', () => {
    it('should validate a complete valid error', () => {
      const error = {
        schemaVersion: 'prediction-error.v1',
        id: 'err-123',
        actual: 0.9,
        predicted: 0.75,
        error: 0.15,
        absoluteError: 0.15,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        sourceRevision: 'a'.repeat(40),
        weight: 0.5,
      };
      const result = validatePredictionError(error);
      expect(result.id).toBe('err-123');
      expect(result.propagated).toBe(true);
      expect(result.weight).toBe(0.5);
    });

    it('should throw for negative absoluteError', () => {
      expect(() =>
        validatePredictionError({
          id: 'err-123',
          actual: 0.9,
          predicted: 0.75,
          error: 0.15,
          absoluteError: -0.1,
          propagated: false,
          node: 'test',
          timestamp: Date.now(),
          traceId: 'trace',
          weight: 0.5,
        })
      ).toThrow(RangeError);
    });

    it('should throw for weight outside [0, 1]', () => {
      expect(() =>
        validatePredictionError({
          id: 'err-123',
          actual: 0.9,
          predicted: 0.75,
          error: 0.15,
          absoluteError: 0.15,
          propagated: false,
          node: 'test',
          timestamp: Date.now(),
          traceId: 'trace',
          weight: 1.5,
        })
      ).toThrow(RangeError);
    });
  });

  describe('isValidPredictionError', () => {
    it('should return true for valid error', () => {
      const error = {
        id: 'err-valid',
        actual: 0.9,
        predicted: 0.75,
        error: 0.15,
        absoluteError: 0.15,
        propagated: false,
        node: 'runtime.test',
        timestamp: Date.now(),
        traceId: 'trace-valid',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(true);
    });

    it('should return false for invalid error', () => {
      expect(isValidPredictionError(null)).toBe(false);
      expect(isValidPredictionError({ id: 'test' })).toBe(false);
    });
  });
});

describe('Bounded Action Plan Schema', () => {
  describe('validateBoundedActionPlan', () => {
    it('should validate a complete valid plan', () => {
      const plan = {
        schemaVersion: 'bounded-action-plan.v1',
        planId: 'plan-123',
        planHash: 'a'.repeat(64),
        traceId: 'trace-456',
        sourceRevision: 'b'.repeat(40),
        createdAt: Date.now(),
        steps: [
          {
            stepId: 'step-1',
            action: 'create_file',
            parameters: { path: '/tmp/test.txt' },
          },
        ],
        maxDurationMs: 5000,
        riskLevel: 'low',
        boundedResources: ['filesystem:/tmp'],
      };
      const result = validateBoundedActionPlan(plan);
      expect(result.planId).toBe('plan-123');
      expect(result.steps).toHaveLength(1);
      expect(result.riskLevel).toBe('low');
    });

    it('should throw for empty steps', () => {
      expect(() =>
        validateBoundedActionPlan({
          planId: 'plan-123',
          planHash: 'a'.repeat(64),
          traceId: 'trace',
          sourceRevision: 'b'.repeat(40),
          createdAt: Date.now(),
          steps: [],
          maxDurationMs: 5000,
          riskLevel: 'low',
        })
      ).toThrow(RangeError);
    });

    it('should throw for invalid riskLevel', () => {
      expect(() =>
        validateBoundedActionPlan({
          planId: 'plan-123',
          planHash: 'a'.repeat(64),
          traceId: 'trace',
          sourceRevision: 'b'.repeat(40),
          createdAt: Date.now(),
          steps: [{ stepId: 's1', action: 'a', parameters: {} }],
          maxDurationMs: 5000,
          riskLevel: 'invalid',
        })
      ).toThrow(RangeError);
    });

    it('should validate step preconditionHash', () => {
      const plan = {
        planId: 'plan-precond',
        planHash: 'a'.repeat(64),
        traceId: 'trace',
        sourceRevision: 'b'.repeat(40),
        createdAt: Date.now(),
        steps: [
          {
            stepId: 'step-1',
            action: 'deploy',
            parameters: {},
            preconditionHash: 'c'.repeat(64),
          },
        ],
        maxDurationMs: 5000,
        riskLevel: 'medium',
      };
      const result = validateBoundedActionPlan(plan);
      expect(result.steps[0].preconditionHash).toBe('c'.repeat(64));
    });
  });

  describe('isValidBoundedActionPlan', () => {
    it('should return true for valid plan', () => {
      const plan = {
        planId: 'plan-valid',
        planHash: 'a'.repeat(64),
        traceId: 'trace-valid',
        sourceRevision: 'b'.repeat(40),
        createdAt: Date.now(),
        steps: [{ stepId: 's1', action: 'a', parameters: {} }],
        maxDurationMs: 5000,
        riskLevel: 'low',
      };
      expect(isValidBoundedActionPlan(plan)).toBe(true);
    });

    it('should return false for invalid plan', () => {
      expect(isValidBoundedActionPlan(null)).toBe(false);
      expect(isValidBoundedActionPlan({ planId: 'test' })).toBe(false);
    });
  });
});

describe('Runtime Action Receipt Schema', () => {
  describe('validateRuntimeActionReceipt', () => {
    it('should validate a complete valid receipt', () => {
      const receipt = {
        schemaVersion: 'runtime-action-receipt.v1',
        receiptId: 'receipt-123',
        actionHash: 'a'.repeat(64),
        traceId: 'trace-456',
        sourceRevision: 'b'.repeat(40),
        executedAt: Date.now(),
        durationMs: 1500,
        outcome: 'succeeded',
        targetResource: 'repo:/path/to/file',
        evidenceHashes: ['c'.repeat(64)],
      };
      const result = validateRuntimeActionReceipt(receipt);
      expect(result.receiptId).toBe('receipt-123');
      expect(result.outcome).toBe('succeeded');
    });

    it('should validate all outcome types', () => {
      const outcomes = ['succeeded', 'failed', 'blocked', 'rolled_back'];
      for (const outcome of outcomes) {
        const receipt = {
          receiptId: 'receipt-test',
          actionHash: 'a'.repeat(64),
          traceId: 'trace',
          sourceRevision: 'b'.repeat(40),
          executedAt: Date.now(),
          durationMs: 100,
          outcome,
        };
        const result = validateRuntimeActionReceipt(receipt);
        expect(result.outcome).toBe(outcome);
      }
    });

    it('should throw for invalid outcome', () => {
      expect(() =>
        validateRuntimeActionReceipt({
          receiptId: 'receipt-123',
          actionHash: 'a'.repeat(64),
          traceId: 'trace',
          sourceRevision: 'b'.repeat(40),
          executedAt: Date.now(),
          durationMs: 100,
          outcome: 'unknown',
        })
      ).toThrow(RangeError);
    });

    it('should throw for negative durationMs', () => {
      expect(() =>
        validateRuntimeActionReceipt({
          receiptId: 'receipt-123',
          actionHash: 'a'.repeat(64),
          traceId: 'trace',
          sourceRevision: 'b'.repeat(40),
          executedAt: Date.now(),
          durationMs: -1,
          outcome: 'succeeded',
        })
      ).toThrow(RangeError);
    });
  });

  describe('isValidRuntimeActionReceipt', () => {
    it('should return true for valid receipt', () => {
      const receipt = {
        receiptId: 'receipt-valid',
        actionHash: 'a'.repeat(64),
        traceId: 'trace-valid',
        sourceRevision: 'b'.repeat(40),
        executedAt: Date.now(),
        durationMs: 100,
        outcome: 'succeeded',
      };
      expect(isValidRuntimeActionReceipt(receipt)).toBe(true);
    });

    it('should return false for invalid receipt', () => {
      expect(isValidRuntimeActionReceipt(null)).toBe(false);
      expect(isValidRuntimeActionReceipt({ receiptId: 'test' })).toBe(false);
    });
  });
});

describe('Predictive Snapshot Schema', () => {
  describe('validatePredictiveSnapshot', () => {
    it('should validate a complete valid snapshot', () => {
      const snapshot = {
        schemaVersion: 'predictive-snapshot.v1',
        snapshotId: 'snap-123',
        sourceRevision: 'a'.repeat(40),
        capturedAt: Date.now(),
        nodeCount: 42,
        synapseCount: 128,
        patternCount: 256,
        avgConfidence: 0.75,
        errorRate: 0.05,
        phase: 'predicting',
      };
      const result = validatePredictiveSnapshot(snapshot);
      expect(result.snapshotId).toBe('snap-123');
      expect(result.phase).toBe('predicting');
    });

    it('should validate all phase types', () => {
      const phases = ['idle', 'predicting', 'error-computing', 'learning'];
      for (const phase of phases) {
        const snapshot = {
          snapshotId: 'snap-test',
          sourceRevision: 'a'.repeat(40),
          capturedAt: Date.now(),
          nodeCount: 10,
          synapseCount: 10,
          patternCount: 10,
          avgConfidence: 0.5,
          errorRate: 0.1,
          phase,
        };
        const result = validatePredictiveSnapshot(snapshot);
        expect(result.phase).toBe(phase);
      }
    });

    it('should throw for invalid phase', () => {
      expect(() =>
        validatePredictiveSnapshot({
          snapshotId: 'snap-123',
          sourceRevision: 'a'.repeat(40),
          capturedAt: Date.now(),
          nodeCount: 10,
          synapseCount: 10,
          patternCount: 10,
          avgConfidence: 0.5,
          errorRate: 0.1,
          phase: 'invalid',
        })
      ).toThrow(RangeError);
    });

    it('should throw for errorRate outside [0, 1]', () => {
      expect(() =>
        validatePredictiveSnapshot({
          snapshotId: 'snap-123',
          sourceRevision: 'a'.repeat(40),
          capturedAt: Date.now(),
          nodeCount: 10,
          synapseCount: 10,
          patternCount: 10,
          avgConfidence: 0.5,
          errorRate: 1.5,
          phase: 'idle',
        })
      ).toThrow(RangeError);
    });
  });

  describe('isValidPredictiveSnapshot', () => {
    it('should return true for valid snapshot', () => {
      const snapshot = {
        snapshotId: 'snap-valid',
        sourceRevision: 'a'.repeat(40),
        capturedAt: Date.now(),
        nodeCount: 10,
        synapseCount: 10,
        patternCount: 10,
        avgConfidence: 0.5,
        errorRate: 0.1,
        phase: 'idle',
      };
      expect(isValidPredictiveSnapshot(snapshot)).toBe(true);
    });

    it('should return false for invalid snapshot', () => {
      expect(isValidPredictiveSnapshot(null)).toBe(false);
      expect(isValidPredictiveSnapshot({ snapshotId: 'test' })).toBe(false);
    });
  });
});

describe('Runtime Readback Schema', () => {
  describe('validateRuntimeReadback', () => {
    it('should validate a verified readback', () => {
      const readback = {
        schemaVersion: 'runtime-readback.v1',
        readbackId: 'rb-123',
        sourceRevision: 'a'.repeat(40),
        targetResource: 'container:latest',
        expectedHash: 'b'.repeat(64),
        actualHash: 'b'.repeat(64),
        status: 'verified',
        readbackAt: Date.now(),
        latencyMs: 50,
      };
      const result = validateRuntimeReadback(readback);
      expect(result.readbackId).toBe('rb-123');
      expect(result.status).toBe('verified');
    });

    it('should validate all status types', () => {
      const statuses = ['verified', 'mismatch', 'unavailable', 'timeout'];
      for (const status of statuses) {
        const readback = {
          readbackId: 'rb-test',
          sourceRevision: 'a'.repeat(40),
          targetResource: 'resource',
          expectedHash: 'b'.repeat(64),
          status,
          readbackAt: Date.now(),
        };
        const result = validateRuntimeReadback(readback);
        expect(result.status).toBe(status);
      }
    });

    it('should throw for invalid status', () => {
      expect(() =>
        validateRuntimeReadback({
          readbackId: 'rb-123',
          sourceRevision: 'a'.repeat(40),
          targetResource: 'resource',
          expectedHash: 'b'.repeat(64),
          status: 'unknown',
          readbackAt: Date.now(),
        })
      ).toThrow(RangeError);
    });
  });

  describe('isValidRuntimeReadback', () => {
    it('should return true for valid readback', () => {
      const readback = {
        readbackId: 'rb-valid',
        sourceRevision: 'a'.repeat(40),
        targetResource: 'resource-valid',
        expectedHash: 'b'.repeat(64),
        status: 'verified',
        readbackAt: Date.now(),
      };
      expect(isValidRuntimeReadback(readback)).toBe(true);
    });

    it('should return false for invalid readback', () => {
      expect(isValidRuntimeReadback(null)).toBe(false);
      expect(isValidRuntimeReadback({ readbackId: 'test' })).toBe(false);
    });
  });
});

describe('Risk Evidence Bundle Schema', () => {
  describe('validateRiskEvidenceBundle', () => {
    it('should validate a complete valid bundle', () => {
      const bundle = {
        schemaVersion: 'risk-evidence-bundle.v1',
        bundleId: 'bundle-123',
        bundleHash: 'a'.repeat(64),
        sourceRevision: 'b'.repeat(40),
        riskLevel: 'high',
        riskCategory: 'security',
        description: 'Unauthorized access attempt detected',
        evidence: [
          {
            evidenceId: 'ev-1',
            evidenceHash: 'c'.repeat(64),
            sourceType: 'log',
            sourceTimestamp: Date.now(),
            description: 'Failed login attempt from unknown IP',
          },
        ],
        detectedAt: Date.now(),
        ownerReviewRequired: true,
        mitigationPlan: 'Block IP and notify security team',
      };
      const result = validateRiskEvidenceBundle(bundle);
      expect(result.bundleId).toBe('bundle-123');
      expect(result.riskLevel).toBe('high');
      expect(result.evidence).toHaveLength(1);
    });

    it('should validate all risk levels', () => {
      const levels = ['negligible', 'low', 'medium', 'high', 'critical'];
      for (const level of levels) {
        const bundle = {
          bundleId: 'bundle-test',
          bundleHash: 'a'.repeat(64),
          sourceRevision: 'b'.repeat(40),
          riskLevel: level,
          riskCategory: 'security',
          description: 'Test risk',
          evidence: [
            {
              evidenceId: 'ev-1',
              evidenceHash: 'c'.repeat(64),
              sourceType: 'log',
              sourceTimestamp: Date.now(),
              description: 'Test evidence',
            },
          ],
          detectedAt: Date.now(),
          ownerReviewRequired: false,
        };
        const result = validateRiskEvidenceBundle(bundle);
        expect(result.riskLevel).toBe(level);
      }
    });

    it('should validate all risk categories', () => {
      const categories = ['security', 'operational', 'compliance', 'performance', 'reliability'];
      for (const category of categories) {
        const bundle = {
          bundleId: 'bundle-test',
          bundleHash: 'a'.repeat(64),
          sourceRevision: 'b'.repeat(40),
          riskLevel: 'low',
          riskCategory: category,
          description: 'Test risk',
          evidence: [
            {
              evidenceId: 'ev-1',
              evidenceHash: 'c'.repeat(64),
              sourceType: 'metric',
              sourceTimestamp: Date.now(),
              description: 'Test evidence',
            },
          ],
          detectedAt: Date.now(),
          ownerReviewRequired: false,
        };
        const result = validateRiskEvidenceBundle(bundle);
        expect(result.riskCategory).toBe(category);
      }
    });

    it('should throw for empty evidence', () => {
      expect(() =>
        validateRiskEvidenceBundle({
          bundleId: 'bundle-123',
          bundleHash: 'a'.repeat(64),
          sourceRevision: 'b'.repeat(40),
          riskLevel: 'high',
          riskCategory: 'security',
          description: 'Test',
          evidence: [],
          detectedAt: Date.now(),
          ownerReviewRequired: true,
        })
      ).toThrow(RangeError);
    });

    it('should throw for invalid riskLevel', () => {
      expect(() =>
        validateRiskEvidenceBundle({
          bundleId: 'bundle-123',
          bundleHash: 'a'.repeat(64),
          sourceRevision: 'b'.repeat(40),
          riskLevel: 'unknown',
          riskCategory: 'security',
          description: 'Test',
          evidence: [
            {
              evidenceId: 'ev-1',
              evidenceHash: 'c'.repeat(64),
              sourceType: 'log',
              sourceTimestamp: Date.now(),
              description: 'Test',
            },
          ],
          detectedAt: Date.now(),
          ownerReviewRequired: false,
        })
      ).toThrow(RangeError);
    });
  });

  describe('isValidRiskEvidenceBundle', () => {
    it('should return true for valid bundle', () => {
      const bundle = {
        bundleId: 'bundle-valid',
        bundleHash: 'a'.repeat(64),
        sourceRevision: 'b'.repeat(40),
        riskLevel: 'low',
        riskCategory: 'operational',
        description: 'Test risk',
        evidence: [
          {
            evidenceId: 'ev-valid',
            evidenceHash: 'c'.repeat(64),
            sourceType: 'runtime',
            sourceTimestamp: Date.now(),
            description: 'Test evidence',
          },
        ],
        detectedAt: Date.now(),
        ownerReviewRequired: false,
      };
      expect(isValidRiskEvidenceBundle(bundle)).toBe(true);
    });

    it('should return false for invalid bundle', () => {
      expect(isValidRiskEvidenceBundle(null)).toBe(false);
      expect(isValidRiskEvidenceBundle({ bundleId: 'test' })).toBe(false);
    });
  });
});
