/**
 * Predictive Inference Types - Unit Tests
 *
 * @module predictive/inference/types.test
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  isReceiptStale,
  validateModelReceipt,
  computeReceiptHash,
  detectChannelConflicts,
  type ModelReceipt,
  type RevisionBinding,
} from './types';

describe('predictive/inference/types', () => {
  const mockRevisionBinding: RevisionBinding = {
    runtimeRevision: 'abc1234',
    configRevision: 'cfg_v1',
    schemaVersion: '1.0',
    boundAt: Date.now(),
  };

  const createMockReceipt = (overrides: Partial<ModelReceipt> = {}): ModelReceipt => ({
    schemaVersion: 'model-receipt.v1',
    receiptId: 'receipt_test_001',
    channelType: 'hard_invariant',
    modelClass: 'test_model',
    implementationVersion: '1.0.0',
    revisionBinding: mockRevisionBinding,
    featureSchemaHash: 'feat_hash_123',
    inputWindowHash: {
      hash: 'window_hash_456',
      signalCount: 10,
      windowStart: Date.now() - 1000,
      windowEnd: Date.now(),
      featureHash: 'feature_789',
    },
    modelStateHash: {
      parametersHash: 'param_hash',
      weightsHash: 'weight_hash',
      configHash: 'config_hash',
      libraryVersion: '1.0.0',
    },
    score: 0.85,
    calibrationMetadata: {
      method: 'cross_validation',
      score: 0.82,
      sampleSize: 1000,
    },
    knownLimitations: [],
    createdAt: Date.now(),
    receiptHash: '',
    ...overrides,
  });

  describe('isReceiptStale', () => {
    it('returns false for fresh receipt with matching revision', () => {
      const receipt = createMockReceipt();
      expect(isReceiptStale(receipt, 'abc1234')).toBe(false);
    });

    it('returns true for receipt with different revision', () => {
      const receipt = createMockReceipt();
      expect(isReceiptStale(receipt, 'different_rev')).toBe(true);
    });

    it('returns true for old receipt beyond maxAgeMs', () => {
      const receipt = createMockReceipt({
        createdAt: Date.now() - 10 * 60 * 1000, // 10 minutes ago
      });
      expect(isReceiptStale(receipt, 'abc1234', 5 * 60 * 1000)).toBe(true);
    });

    it('returns false for receipt within maxAgeMs', () => {
      const receipt = createMockReceipt({
        createdAt: Date.now() - 2 * 60 * 1000, // 2 minutes ago
      });
      expect(isReceiptStale(receipt, 'abc1234', 5 * 60 * 1000)).toBe(false);
    });
  });

  describe('validateModelReceipt', () => {
    it('returns valid for well-formed receipt', () => {
      const receipt = createMockReceipt();
      receipt.receiptHash = computeReceiptHash(receipt);
      const result = validateModelReceipt(receipt);
      expect(result.isValid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('returns invalid for null input', () => {
      const result = validateModelReceipt(null);
      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Receipt is not an object');
    });

    it('returns invalid for missing schemaVersion', () => {
      const receipt = createMockReceipt({ schemaVersion: undefined });
      const result = validateModelReceipt(receipt);
      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Missing schemaVersion');
    });

    it('returns invalid for missing receiptId', () => {
      const receipt = createMockReceipt({ receiptId: '' });
      const result = validateModelReceipt(receipt);
      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Missing receiptId');
    });

    it('returns invalid for missing revisionBinding', () => {
      const receipt = createMockReceipt({ revisionBinding: undefined });
      const result = validateModelReceipt(receipt);
      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Missing revisionBinding');
    });

    it('returns invalid for missing inputWindowHash', () => {
      const receipt = createMockReceipt({ inputWindowHash: undefined });
      const result = validateModelReceipt(receipt);
      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Missing inputWindowHash');
    });

    it('returns invalid for missing modelStateHash', () => {
      const receipt = createMockReceipt({ modelStateHash: undefined });
      const result = validateModelReceipt(receipt);
      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Missing modelStateHash');
    });

    it('warns about missing score', () => {
      const receipt = createMockReceipt({ score: undefined });
      const result = validateModelReceipt(receipt);
      expect(result.warnings).toContain('Missing score');
    });

    it('warns about missing calibration metadata', () => {
      const receipt = createMockReceipt({ calibrationMetadata: undefined });
      const result = validateModelReceipt(receipt);
      expect(result.warnings).toContain('No calibration metadata');
    });

    it('warns about empty limitations list', () => {
      const receipt = createMockReceipt({ knownLimitations: [] });
      const result = validateModelReceipt(receipt);
      expect(result.warnings).toContain('No documented limitations');
    });

    it('computes binding age correctly', () => {
      const fiveMinutesAgo = Date.now() - 5 * 60 * 1000;
      const receipt = createMockReceipt({ createdAt: fiveMinutesAgo });
      const result = validateModelReceipt(receipt);
      expect(result.bindingAgeMs).toBeGreaterThanOrEqual(5 * 60 * 1000 - 100);
      expect(result.bindingAgeMs).toBeLessThan(5 * 60 * 1000 + 100);
    });
  });

  describe('computeReceiptHash', () => {
    it('produces consistent hash for same input', () => {
      const receipt = createMockReceipt();
      const hash1 = computeReceiptHash(receipt);
      const hash2 = computeReceiptHash(receipt);
      expect(hash1).toBe(hash2);
    });

    it('produces different hash for different inputs', () => {
      const receipt1 = createMockReceipt({ receiptId: 'receipt_1' });
      const receipt2 = createMockReceipt({ receiptId: 'receipt_2' });
      const hash1 = computeReceiptHash(receipt1);
      const hash2 = computeReceiptHash(receipt2);
      expect(hash1).not.toBe(hash2);
    });

    it('produces hash with receipt_ prefix', () => {
      const receipt = createMockReceipt();
      const hash = computeReceiptHash(receipt);
      expect(hash).toMatch(/^receipt_[0-9a-f]+$/);
    });
  });

  describe('detectChannelConflicts', () => {
    it('returns false for single receipt', () => {
      const receipt = createMockReceipt();
      expect(detectChannelConflicts([receipt])).toBe(false);
    });

    it('returns false for empty array', () => {
      expect(detectChannelConflicts([])).toBe(false);
    });

    it('returns true for mixed pass/fail rates around 50%', () => {
      const receipts = [
        createMockReceipt({ receiptId: 'r1', abortReason: undefined }),
        createMockReceipt({ receiptId: 'r2', abortReason: 'error' }),
        createMockReceipt({ receiptId: 'r3', abortReason: undefined }),
        createMockReceipt({ receiptId: 'r4', abortReason: 'error' }),
      ];
      expect(detectChannelConflicts(receipts)).toBe(true);
    });

    it('returns false for unanimous pass', () => {
      const receipts = [
        createMockReceipt({ receiptId: 'r1', abortReason: undefined }),
        createMockReceipt({ receiptId: 'r2', abortReason: undefined }),
        createMockReceipt({ receiptId: 'r3', abortReason: undefined }),
      ];
      expect(detectChannelConflicts(receipts)).toBe(false);
    });

    it('returns false for unanimous fail', () => {
      const receipts = [
        createMockReceipt({ receiptId: 'r1', abortReason: 'error1' }),
        createMockReceipt({ receiptId: 'r2', abortReason: 'error2' }),
        createMockReceipt({ receiptId: 'r3', abortReason: 'error3' }),
      ];
      expect(detectChannelConflicts(receipts)).toBe(false);
    });
  });
});
