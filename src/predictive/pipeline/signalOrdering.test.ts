/**
 * Tests for Signal Ordering
 *
 * @module predictive/pipeline/signalOrdering.test
 */

import { describe, it, expect } from 'vitest';
import {
  validateOrderingMetadata,
  toOrderedSignal,
  orderSignals,
  validateCanonicalOrder,
  detectSequenceGaps,
  groupByNode,
  validateRevisionBound,
  generateOrderingReceipt,
  SignalOrderingError,
} from './signalOrdering';
import type { Signal } from '../types';

function createSignal(overrides: Partial<Signal> & { tick: number; sequence: number; revision: string }): Signal {
  const { tick, sequence, revision, metadata, ...rest } = overrides;
  return {
    id: 'sig-1',
    node: 'node-a',
    value: 1,
    timestamp: Date.now(),
    traceId: 'trace-1',
    metadata: {
      tick,
      sequence,
      revision,
      ...metadata,
    },
    ...rest,
  };
}

describe('signalOrdering', () => {
  // ========== validateOrderingMetadata ==========
  describe('validateOrderingMetadata', () => {
    it('should return metadata for valid signal', () => {
      const signal = createSignal({ tick: 5, sequence: 10, revision: 'rev-abc' });
      const result = validateOrderingMetadata(signal);
      expect(result).toEqual({
        tick: 5,
        sequence: 10,
        revision: 'rev-abc',
        node: 'node-a',
      });
    });

    it('should throw for missing tick', () => {
      const signal = createSignal({ tick: 5, sequence: 10, revision: 'rev-abc' });
      delete signal.metadata!.tick;
      expect(() => validateOrderingMetadata(signal)).toThrow(SignalOrderingError);
    });

    it('should throw for invalid tick', () => {
      const signal = createSignal({ tick: -1, sequence: 10, revision: 'rev-abc' });
      expect(() => validateOrderingMetadata(signal)).toThrow('non-negative integer');
    });

    it('should throw for missing sequence', () => {
      const signal = createSignal({ tick: 5, sequence: 10, revision: 'rev-abc' });
      delete signal.metadata!.sequence;
      expect(() => validateOrderingMetadata(signal)).toThrow(SignalOrderingError);
    });

    it('should throw for missing revision', () => {
      const signal = createSignal({ tick: 5, sequence: 10, revision: '' });
      expect(() => validateOrderingMetadata(signal)).toThrow(SignalOrderingError);
    });
  });

  // ========== toOrderedSignal ==========
  describe('toOrderedSignal', () => {
    it('should convert signal to ordered signal', () => {
      const signal = createSignal({ tick: 5, sequence: 10, revision: 'rev-abc' });
      const result = toOrderedSignal(signal);
      expect(result.metadata.tick).toBe(5);
      expect(result.metadata.sequence).toBe(10);
      expect(result.metadata.revision).toBe('rev-abc');
    });
  });

  // ========== orderSignals ==========
  describe('orderSignals', () => {
    it('should order signals by tick, node, sequence', () => {
      const signals = [
        createSignal({ id: '3', node: 'node-b', tick: 1, sequence: 1, revision: 'rev-1' }),
        createSignal({ id: '1', node: 'node-a', tick: 1, sequence: 0, revision: 'rev-1' }),
        createSignal({ id: '2', node: 'node-a', tick: 0, sequence: 0, revision: 'rev-1' }),
      ];

      const result = orderSignals(signals);
      expect(result.map((s) => s.id)).toEqual(['2', '1', '3']);
    });

    it('should handle empty array', () => {
      const result = orderSignals([]);
      expect(result).toEqual([]);
    });
  });

  // ========== validateCanonicalOrder ==========
  describe('validateCanonicalOrder', () => {
    it('should pass for correctly ordered signals', () => {
      const signals = [
        createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1' }),
        createSignal({ id: '2', tick: 0, sequence: 1, revision: 'rev-1' }),
        createSignal({ id: '3', tick: 1, sequence: 0, revision: 'rev-1' }),
      ];

      expect(() => validateCanonicalOrder(signals as any)).not.toThrow();
    });

    it('should throw for tick regression', () => {
      const signals = [
        createSignal({ id: '1', tick: 1, sequence: 0, revision: 'rev-1' }),
        createSignal({ id: '2', tick: 0, sequence: 0, revision: 'rev-1' }),
      ];

      expect(() => validateCanonicalOrder(signals as any)).toThrow('Tick regression');
    });
  });

  // ========== detectSequenceGaps ==========
  describe('detectSequenceGaps', () => {
    it('should detect sequence gaps', () => {
      const signals = [
        createSignal({ id: '1', node: 'node-a', tick: 0, sequence: 0, revision: 'rev-1' }),
        createSignal({ id: '2', node: 'node-a', tick: 0, sequence: 1, revision: 'rev-1' }),
        createSignal({ id: '3', node: 'node-a', tick: 0, sequence: 3, revision: 'rev-1' }), // Gap!
      ];

      const gaps = detectSequenceGaps(signals as any);
      expect(gaps).toHaveLength(1);
      expect(gaps[0]).toMatchObject({
        tick: 0,
        node: 'node-a',
        expectedSequence: 2,
        actualSequence: 3,
        gapSize: 1,
      });
    });

    it('should return empty for no gaps', () => {
      const signals = [
        createSignal({ id: '1', node: 'node-a', tick: 0, sequence: 0, revision: 'rev-1' }),
        createSignal({ id: '2', node: 'node-a', tick: 0, sequence: 1, revision: 'rev-1' }),
        createSignal({ id: '3', node: 'node-a', tick: 0, sequence: 2, revision: 'rev-1' }),
      ];

      const gaps = detectSequenceGaps(signals as any);
      expect(gaps).toHaveLength(0);
    });
  });

  // ========== groupByNode ==========
  describe('groupByNode', () => {
    it('should group signals by node', () => {
      const signals = [
        createSignal({ id: '1', node: 'node-a', tick: 0, sequence: 0, revision: 'rev-1' }),
        createSignal({ id: '2', node: 'node-b', tick: 0, sequence: 0, revision: 'rev-1' }),
        createSignal({ id: '3', node: 'node-a', tick: 1, sequence: 0, revision: 'rev-1' }),
      ];

      const groups = groupByNode(signals as any);
      expect(groups.get('node-a')).toHaveLength(2);
      expect(groups.get('node-b')).toHaveLength(1);
    });
  });

  // ========== validateRevisionBound ==========
  describe('validateRevisionBound', () => {
    it('should pass when all signals have same revision', () => {
      const signals = [
        createSignal({ id: '1', revision: 'rev-abc' }),
        createSignal({ id: '2', revision: 'rev-abc' }),
      ];

      expect(() => validateRevisionBound(signals as any)).not.toThrow();
    });

    it('should throw when signals have different revisions', () => {
      const signals = [
        createSignal({ id: '1', revision: 'rev-abc' }),
        createSignal({ id: '2', revision: 'rev-xyz' }),
      ];

      expect(() => validateRevisionBound(signals as any)).toThrow('Multiple revisions');
    });

    it('should validate against expected revision', () => {
      const signals = [createSignal({ id: '1', revision: 'rev-abc' })];

      expect(() => validateRevisionBound(signals as any, 'rev-xyz')).toThrow('Revision mismatch');
      expect(() => validateRevisionBound(signals as any, 'rev-abc')).not.toThrow();
    });
  });

  // ========== generateOrderingReceipt ==========
  describe('generateOrderingReceipt', () => {
    it('should generate receipt for ordered signals', () => {
      const signals = [
        createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-abc' }),
        createSignal({ id: '2', tick: 1, sequence: 0, revision: 'rev-abc' }),
      ];

      const receipt = generateOrderingReceipt(signals as any);
      expect(receipt.tickRange).toEqual([0, 1]);
      expect(receipt.revision).toBe('rev-abc');
      expect(receipt.signalCount).toBe(2);
    });

    it('should handle empty signals', () => {
      const receipt = generateOrderingReceipt([]);
      expect(receipt.signalCount).toBe(0);
      expect(receipt.tickRange).toEqual([0, 0]);
    });
  });
});
