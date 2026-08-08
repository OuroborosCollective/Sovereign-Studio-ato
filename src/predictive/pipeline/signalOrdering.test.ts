/**
 * Signal Ordering Tests
 *
 * Tests for deterministic signal ordering by tick, node, and sequence.
 *
 * @module predictive/pipeline/signalOrdering.test
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  extractTick,
  extractSequence,
  createOrderKey,
  compareOrderKeys,
  withOrderKey,
  orderSignals,
  groupByNode,
  verifyOrder,
  type SignalOrderKey,
  type OrderedSignal,
} from './signalOrdering';
import type { Signal } from '../types';

describe('Signal Ordering', () => {
  describe('extractTick', () => {
    it('should extract tick from metadata', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: 1000,
        traceId: 'trace-1',
        metadata: { _tick: 42 },
      };

      expect(extractTick(signal)).toBe(42);
    });

    it('should extract tick from custom field', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: 1000,
        traceId: 'trace-1',
        metadata: { customTick: 99 },
      };

      expect(extractTick(signal, { tickField: 'customTick' })).toBe(99);
    });

    it('should derive tick from timestamp when not in metadata', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: 1500,
        traceId: 'trace-1',
      };

      expect(extractTick(signal)).toBe(1); // floor(1500/1000)
    });
  });

  describe('extractSequence', () => {
    it('should extract sequence from metadata', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: 1000,
        traceId: 'trace-1',
        metadata: { _seq: 5 },
      };

      expect(extractSequence(signal)).toBe(5);
    });

    it('should return 0 when sequence not in metadata', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: 1000,
        traceId: 'trace-1',
      };

      expect(extractSequence(signal)).toBe(0);
    });
  });

  describe('createOrderKey', () => {
    it('should create order key from signal', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: 1000,
        traceId: 'trace-1',
        metadata: { _tick: 1, _seq: 2 },
      };

      const key = createOrderKey(signal);

      expect(key).toEqual({
        tick: 1,
        node: 'test.node',
        sequence: 2,
      });
    });
  });

  describe('compareOrderKeys', () => {
    it('should return 0 for equal keys', () => {
      const a: SignalOrderKey = { tick: 1, node: 'a', sequence: 0 };
      const b: SignalOrderKey = { tick: 1, node: 'a', sequence: 0 };

      expect(compareOrderKeys(a, b)).toBe(0);
    });

    it('should sort by tick first', () => {
      const a: SignalOrderKey = { tick: 1, node: 'a', sequence: 0 };
      const b: SignalOrderKey = { tick: 2, node: 'a', sequence: 0 };

      expect(compareOrderKeys(a, b)).toBeLessThan(0);
      expect(compareOrderKeys(b, a)).toBeGreaterThan(0);
    });

    it('should sort by node second', () => {
      const a: SignalOrderKey = { tick: 1, node: 'a', sequence: 0 };
      const b: SignalOrderKey = { tick: 1, node: 'b', sequence: 0 };

      expect(compareOrderKeys(a, b)).toBeLessThan(0);
      expect(compareOrderKeys(b, a)).toBeGreaterThan(0);
    });

    it('should sort by sequence third', () => {
      const a: SignalOrderKey = { tick: 1, node: 'a', sequence: 0 };
      const b: SignalOrderKey = { tick: 1, node: 'a', sequence: 1 };

      expect(compareOrderKeys(a, b)).toBeLessThan(0);
      expect(compareOrderKeys(b, a)).toBeGreaterThan(0);
    });

    it('should be deterministic for same input', () => {
      const a: SignalOrderKey = { tick: 1, node: 'node-x', sequence: 5 };
      const b: SignalOrderKey = { tick: 1, node: 'node-x', sequence: 5 };

      // Multiple comparisons should always return 0
      expect(compareOrderKeys(a, b)).toBe(0);
      expect(compareOrderKeys(a, b)).toBe(0);
      expect(compareOrderKeys(a, b)).toBe(0);
    });
  });

  describe('withOrderKey', () => {
    it('should attach order key to signal without mutation', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: 1000,
        traceId: 'trace-1',
        metadata: { _tick: 1, _seq: 2 },
      };

      const ordered = withOrderKey(signal);

      expect(ordered.id).toBe('sig-1');
      expect(ordered.node).toBe('test.node');
      expect(ordered.orderKey).toEqual({
        tick: 1,
        node: 'test.node',
        sequence: 2,
      });
    });
  });

  describe('orderSignals', () => {
    it('should sort signals by tick, node, sequence', () => {
      const signals: Signal[] = [
        { id: '3', node: 'b', value: 0.3, timestamp: 1000, traceId: 't', metadata: { _tick: 1, _seq: 1 } },
        { id: '1', node: 'a', value: 0.1, timestamp: 1000, traceId: 't', metadata: { _tick: 1, _seq: 0 } },
        { id: '4', node: 'b', value: 0.4, timestamp: 1000, traceId: 't', metadata: { _tick: 2, _seq: 0 } },
        { id: '2', node: 'a', value: 0.2, timestamp: 1000, traceId: 't', metadata: { _tick: 1, _seq: 1 } },
      ];

      const ordered = orderSignals(signals);

      expect(ordered.map((s) => s.id)).toEqual(['1', '2', '3', '4']);
    });

    it('should be deterministic - same input produces same output', () => {
      const signals: Signal[] = [
        { id: '1', node: 'node-a', value: 0.1, timestamp: 1000, traceId: 't', metadata: { _tick: 1, _seq: 0 } },
        { id: '2', node: 'node-b', value: 0.2, timestamp: 1100, traceId: 't', metadata: { _tick: 1, _seq: 1 } },
        { id: '3', node: 'node-a', value: 0.3, timestamp: 1200, traceId: 't', metadata: { _tick: 2, _seq: 0 } },
      ];

      const result1 = orderSignals(signals);
      const result2 = orderSignals(signals);

      expect(result1.map((s) => s.id)).toEqual(result2.map((s) => s.id));
    });

    it('should handle empty array', () => {
      const ordered = orderSignals([]);
      expect(ordered).toEqual([]);
    });

    it('should handle single signal', () => {
      const signals: Signal[] = [
        { id: '1', node: 'a', value: 0.1, timestamp: 1000, traceId: 't', metadata: { _tick: 1, _seq: 0 } },
      ];

      const ordered = orderSignals(signals);
      expect(ordered.length).toBe(1);
      expect(ordered[0].id).toBe('1');
    });

    it('should handle signals without tick/seq in metadata', () => {
      const signals: Signal[] = [
        { id: '1', node: 'b', value: 0.1, timestamp: 2000, traceId: 't' },
        { id: '2', node: 'a', value: 0.2, timestamp: 1000, traceId: 't' },
      ];

      const ordered = orderSignals(signals);

      // Both will have tick 1 (from timestamp), node sorts alphabetically
      expect(ordered[0].id).toBe('2');
      expect(ordered[1].id).toBe('1');
    });
  });

  describe('groupByNode', () => {
    it('should group signals by node', () => {
      const ordered: OrderedSignal[] = [
        { id: '1', node: 'a', value: 0.1, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 0 } },
        { id: '2', node: 'b', value: 0.2, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'b', sequence: 0 } },
        { id: '3', node: 'a', value: 0.3, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 1 } },
      ];

      const groups = groupByNode(ordered);

      expect(groups.get('a')?.length).toBe(2);
      expect(groups.get('b')?.length).toBe(1);
    });

    it('should preserve order within groups', () => {
      const ordered: OrderedSignal[] = [
        { id: '1', node: 'a', value: 0.1, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 0 } },
        { id: '2', node: 'a', value: 0.2, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 1 } },
      ];

      const groups = groupByNode(ordered);
      const nodeA = groups.get('a')!;

      expect(nodeA[0].id).toBe('1');
      expect(nodeA[1].id).toBe('2');
    });
  });

  describe('verifyOrder', () => {
    it('should return true for correctly ordered signals', () => {
      const ordered: OrderedSignal[] = [
        { id: '1', node: 'a', value: 0.1, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 0 } },
        { id: '2', node: 'a', value: 0.2, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 1 } },
        { id: '3', node: 'b', value: 0.3, timestamp: 1000, traceId: 't', orderKey: { tick: 2, node: 'b', sequence: 0 } },
      ];

      expect(verifyOrder(ordered)).toBe(true);
    });

    it('should return false for incorrectly ordered signals', () => {
      const ordered: OrderedSignal[] = [
        { id: '2', node: 'a', value: 0.2, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 1 } },
        { id: '1', node: 'a', value: 0.1, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 0 } },
      ];

      expect(verifyOrder(ordered)).toBe(false);
    });

    it('should return true for empty array', () => {
      expect(verifyOrder([])).toBe(true);
    });

    it('should return true for single element', () => {
      const ordered: OrderedSignal[] = [
        { id: '1', node: 'a', value: 0.1, timestamp: 1000, traceId: 't', orderKey: { tick: 1, node: 'a', sequence: 0 } },
      ];

      expect(verifyOrder(ordered)).toBe(true);
    });
  });

  describe('Replay Parity', () => {
    it('should produce identical results when replayed', () => {
      const originalSignals: Signal[] = [
        { id: '1', node: 'node-x', value: 0.1, timestamp: 1000, traceId: 'trace-1', metadata: { _tick: 1, _seq: 0 } },
        { id: '2', node: 'node-y', value: 0.2, timestamp: 1100, traceId: 'trace-2', metadata: { _tick: 1, _seq: 1 } },
        { id: '3', node: 'node-x', value: 0.3, timestamp: 1200, traceId: 'trace-3', metadata: { _tick: 2, _seq: 0 } },
      ];

      // First pass
      const ordered1 = orderSignals(originalSignals);

      // Simulate "replay" by calling again with same data
      const ordered2 = orderSignals(originalSignals);

      // Verify identical ordering
      expect(ordered1.map((s) => s.id)).toEqual(ordered2.map((s) => s.id));
      expect(ordered1.map((s) => s.orderKey.tick)).toEqual(ordered2.map((s) => s.orderKey.tick));
      expect(ordered1.map((s) => s.orderKey.node)).toEqual(ordered2.map((s) => s.orderKey.node));
      expect(ordered1.map((s) => s.orderKey.sequence)).toEqual(ordered2.map((s) => s.orderKey.sequence));
    });

    it('should produce identical order hashes for replay', () => {
      const signals: Signal[] = [
        { id: '1', node: 'a', value: 0.1, timestamp: 1000, traceId: 't', metadata: { _tick: 1, _seq: 0 } },
        { id: '2', node: 'b', value: 0.2, timestamp: 1000, traceId: 't', metadata: { _tick: 1, _seq: 1 } },
      ];

      const ordered = orderSignals(signals);

      // Compute deterministic hash from order
      const orderHash = ordered
        .map((s) => `${s.orderKey.tick}:${s.orderKey.node}:${s.orderKey.sequence}`)
        .join('|');

      // Same signals should produce same hash
      const replayOrdered = orderSignals(signals);
      const replayHash = replayOrdered
        .map((s) => `${s.orderKey.tick}:${s.orderKey.node}:${s.orderKey.sequence}`)
        .join('|');

      expect(orderHash).toBe(replayHash);
    });
  });
});
