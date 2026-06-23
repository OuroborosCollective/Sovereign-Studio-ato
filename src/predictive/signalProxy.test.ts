/**
 * Signal Proxy Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  SignalBufferManager,
  DirectSignalEmitter,
  createSignalProxy,
  createDefaultSignalProxyConfig,
} from './signalProxy';
import type { Signal } from './types';

describe('SignalBufferManager', () => {
  let buffer: SignalBufferManager;

  beforeEach(() => {
    buffer = new SignalBufferManager(100);
  });

  describe('push', () => {
    it('should add signals to buffer', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.8,
        timestamp: Date.now(),
        traceId: 'trace-1',
      };

      buffer.push('test.node', signal);

      const signals = buffer.peek('test.node');
      expect(signals.length).toBe(1);
      expect(signals[0].id).toBe('sig-1');
    });

    it('should use circular buffer when full', () => {
      // Fill buffer
      for (let i = 0; i < 100; i++) {
        const signal: Signal = {
          id: `sig-${i}`,
          node: 'test.node',
          value: i / 100,
          timestamp: Date.now(),
          traceId: `trace-${i}`,
        };
        buffer.push('test.node', signal);
      }

      expect(buffer.peek('test.node').length).toBe(100);

      // Add one more - should evict oldest
      const newSignal: Signal = {
        id: 'sig-new',
        node: 'test.node',
        value: 1.0,
        timestamp: Date.now(),
        traceId: 'trace-new',
      };
      buffer.push('test.node', newSignal);

      const signals = buffer.peek('test.node');
      expect(signals.length).toBe(100);
      expect(signals[0].id).toBe('sig-1'); // First should be gone
      expect(signals[99].id).toBe('sig-new');
    });

    it('should track timestamps correctly', () => {
      const now = Date.now();
      const signal1: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: now,
        traceId: 'trace-1',
      };
      const signal2: Signal = {
        id: 'sig-2',
        node: 'test.node',
        value: 0.6,
        timestamp: now + 10,
        traceId: 'trace-2',
      };

      buffer.push('test.node', signal1);
      buffer.push('test.node', signal2);

      expect(buffer.peek('test.node').length).toBe(2);
    });
  });

  describe('flush', () => {
    it('should return and clear all signals', () => {
      for (let i = 0; i < 5; i++) {
        const signal: Signal = {
          id: `sig-${i}`,
          node: 'test.node',
          value: 0.5,
          timestamp: Date.now(),
          traceId: `trace-${i}`,
        };
        buffer.push('test.node', signal);
      }

      const flushed = buffer.flush();

      expect(flushed.length).toBe(5);
      expect(buffer.peek('test.node').length).toBe(0);
    });

    it('should flush all buffers', () => {
      buffer.push('node-a', {
        id: 'sig-a',
        node: 'node-a',
        value: 0.5,
        timestamp: Date.now(),
        traceId: 'trace-1',
      });
      buffer.push('node-b', {
        id: 'sig-b',
        node: 'node-b',
        value: 0.6,
        timestamp: Date.now(),
        traceId: 'trace-2',
      });

      const flushed = buffer.flush();

      expect(flushed.length).toBe(2);
    });

    it('should call onFlush callback', () => {
      let callbackCalled = false;
      buffer.setEmitter((signals) => {
        callbackCalled = true;
        expect(signals.length).toBe(2);
      });

      buffer.push('test', { id: '1', node: 't', value: 0.5, timestamp: 1, traceId: 'tr' } as Signal);
      buffer.push('test', { id: '2', node: 't', value: 0.6, timestamp: 2, traceId: 'tr' } as Signal);
      buffer.flush();

      expect(callbackCalled).toBe(true);
    });
  });

  describe('peek', () => {
    it('should return signals without clearing', () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'test.node',
        value: 0.5,
        timestamp: Date.now(),
        traceId: 'trace-1',
      };
      buffer.push('test.node', signal);

      const peeked = buffer.peek('test.node');
      expect(peeked.length).toBe(1);

      // Should still be there after peek
      expect(buffer.peek('test.node').length).toBe(1);
    });

    it('should return empty array for unknown buffer', () => {
      const peeked = buffer.peek('unknown.node');
      expect(peeked.length).toBe(0);
    });
  });

  describe('getTotalCount', () => {
    it('should return total signals across all buffers', () => {
      buffer.push('node-a', { id: '1', node: 'a', value: 0.5, timestamp: 1, traceId: 'tr' } as Signal);
      buffer.push('node-b', { id: '2', node: 'b', value: 0.5, timestamp: 1, traceId: 'tr' } as Signal);
      buffer.push('node-a', { id: '3', node: 'a', value: 0.5, timestamp: 1, traceId: 'tr' } as Signal);

      expect(buffer.getTotalCount()).toBe(3);
    });
  });

  describe('clear', () => {
    it('should clear all buffers', () => {
      buffer.push('node-a', { id: '1', node: 'a', value: 0.5, timestamp: 1, traceId: 'tr' } as Signal);
      buffer.push('node-b', { id: '2', node: 'b', value: 0.5, timestamp: 1, traceId: 'tr' } as Signal);

      buffer.clear();

      expect(buffer.getTotalCount()).toBe(0);
      expect(buffer.getBufferIds().length).toBe(0);
    });
  });

  describe('getBufferIds', () => {
    it('should return all buffer IDs', () => {
      buffer.push('node-a', { id: '1', node: 'a', value: 0.5, timestamp: 1, traceId: 'tr' } as Signal);
      buffer.push('node-b', { id: '2', node: 'b', value: 0.5, timestamp: 1, traceId: 'tr' } as Signal);

      const ids = buffer.getBufferIds();
      expect(ids).toContain('node-a');
      expect(ids).toContain('node-b');
      expect(ids.length).toBe(2);
    });
  });
});

describe('DirectSignalEmitter', () => {
  let emitter: DirectSignalEmitter;
  let traceIdCounter = 0;

  const traceIdProvider = () => `trace-${++traceIdCounter}`;

  beforeEach(() => {
    emitter = new DirectSignalEmitter(100, traceIdProvider);
  });

  describe('emit', () => {
    it('should emit a signal and return it', () => {
      const signal = emitter.emit('test.node', 0.85, { type: 'test' });

      expect(signal.node).toBe('test.node');
      expect(signal.value).toBe(0.85);
      expect(signal.metadata).toEqual({ type: 'test' });
      expect(signal.traceId).toBe('trace-1');
      expect(signal.timestamp).toBeGreaterThan(0);
    });

    it('should increment signal count', () => {
      emitter.emit('test.node', 0.5);
      emitter.emit('test.node', 0.6);
      emitter.emit('test.node', 0.7);

      expect(emitter.getPendingCount()).toBe(3);
    });
  });

  describe('emitBatch', () => {
    it('should emit multiple signals', () => {
      const signals = emitter.emitBatch([
        { node: 'node-a', value: 0.5 },
        { node: 'node-b', value: 0.6 },
      ]);

      expect(signals.length).toBe(2);
      expect(signals[0].node).toBe('node-a');
      expect(signals[1].node).toBe('node-b');
    });
  });

  describe('subscribe', () => {
    it('should receive emitted signals', () => {
      const receivedSignals: Signal[] = [];
      emitter.subscribe((signals) => {
        receivedSignals.push(...signals);
      });

      emitter.emit('node-a', 0.5);
      emitter.emit('node-b', 0.6);
      emitter.flush();

      expect(receivedSignals.length).toBe(2);
    });

    it('should return unsubscribe function', () => {
      const receivedSignals: Signal[] = [];
      const unsubscribe = emitter.subscribe((signals) => {
        receivedSignals.push(...signals);
      });

      emitter.emit('node-a', 0.5);
      emitter.flush();

      unsubscribe();

      emitter.emit('node-b', 0.6);

      expect(receivedSignals.length).toBe(1);
    });
  });

  describe('flush', () => {
    it('should return and clear pending signals', () => {
      emitter.emit('node-a', 0.5);
      emitter.emit('node-b', 0.6);

      const flushed = emitter.flush();

      expect(flushed.length).toBe(2);
      expect(emitter.getPendingCount()).toBe(0);
    });
  });

  describe('peek', () => {
    it('should return signals without flushing', () => {
      emitter.emit('node-a', 0.5);

      const peeked = emitter.peek('node-a');
      expect(peeked.length).toBe(1);
      expect(emitter.getPendingCount()).toBe(1);
    });
  });

  describe('clear', () => {
    it('should clear all pending signals', () => {
      emitter.emit('node-a', 0.5);
      emitter.emit('node-b', 0.6);

      emitter.clear();

      expect(emitter.getPendingCount()).toBe(0);
    });
  });
});

describe('createSignalProxy', () => {
  it('should create a proxy for an object', () => {
    const target = { value: 0.5, count: 10 };
    const buffer = new SignalBufferManager(100);

    const { proxy, flush, destroy } = createSignalProxy(
      'test',
      target,
      () => 'trace-1',
      buffer,
      createDefaultSignalProxyConfig(),
    );

    // Access a property
    const value = proxy.value;

    expect(value).toBe(0.5);

    flush();
    destroy();
  });

  it('should intercept property access', () => {
    const target = { value: 0.5 };
    const buffer = new SignalBufferManager(100);

    const { proxy, flush, getInterceptedPaths, destroy } = createSignalProxy(
      'test',
      target,
      () => 'trace-1',
      buffer,
      createDefaultSignalProxyConfig(),
    );

    // Access properties
    const _ = proxy.value;
    const __ = proxy.count;

    expect(getInterceptedPaths().length).toBeGreaterThan(0);

    flush();
    destroy();
  });

  it('should track property changes', () => {
    const target = { value: 0.5 };
    const buffer = new SignalBufferManager(100);

    const { proxy, flush, destroy } = createSignalProxy(
      'test',
      target,
      () => 'trace-1',
      buffer,
      createDefaultSignalProxyConfig(),
    );

    // Change property
    proxy.value = 0.8;

    const signals = buffer.peek('test');
    // Should have initial signal + change signal
    expect(signals.length).toBeGreaterThanOrEqual(1);

    flush();
    destroy();
  });
});

describe('createDefaultSignalProxyConfig', () => {
  it('should return valid config', () => {
    const config = createDefaultSignalProxyConfig();

    expect(config.enabled).toBe(true);
    expect(config.batchSize).toBeGreaterThan(0);
    expect(config.flushIntervalMs).toBeGreaterThanOrEqual(0);
    expect(config.interceptAll).toBe(true);
  });

  it('should allow overrides', () => {
    const config = createDefaultSignalProxyConfig({
      batchSize: 50,
      enabled: false,
    });

    expect(config.batchSize).toBe(50);
    expect(config.enabled).toBe(false);
  });
});
