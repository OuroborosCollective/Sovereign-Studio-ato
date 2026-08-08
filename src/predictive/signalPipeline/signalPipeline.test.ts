/**
 * Signal Pipeline Tests
 * 
 * @module predictive/signalPipeline
 */

import {
  validateSignalTick,
  validateSignalWindow,
  generateSignalTickSchemaHash,
  generateSignalWindowSchemaHash,
  SIGNAL_TICK_SCHEMA_ID,
  SIGNAL_WINDOW_SCHEMA_ID,
} from './signalTick';

import {
  BackpressureController,
  ReplayParityValidator,
  createSignalTick,
  DEFAULT_BACKPRESSURE_CONFIG,
} from './signalProcessor';

import { BoundedSignalIterator } from './signalProcessor';

describe('signalTick', () => {
  describe('validateSignalTick', () => {
    it('validates a correct signal tick', () => {
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-123',
        sequence: 1,
        tick: 1,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };

      const result = validateSignalTick(tick);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects non-object input', () => {
      const result = validateSignalTick(null);
      expect(result.valid).toBe(false);
      expect(result.errors[0].code).toBe('INVALID_TYPE');
    });

    it('rejects invalid schemaId', () => {
      const tick = {
        schemaId: 'wrong-schema',
        schemaVersion: 'v1',
        id: 'tick-123',
        sequence: 1,
        tick: 1,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };

      const result = validateSignalTick(tick);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'schemaId')).toBe(true);
    });

    it('rejects invalid schemaVersion', () => {
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: '1',
        id: 'tick-123',
        sequence: 1,
        tick: 1,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };

      const result = validateSignalTick(tick);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'schemaVersion')).toBe(true);
    });

    it('rejects negative sequence', () => {
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-123',
        sequence: -1,
        tick: 1,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };

      const result = validateSignalTick(tick);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'sequence')).toBe(true);
    });

    it('rejects empty id', () => {
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: '',
        sequence: 1,
        tick: 1,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };

      const result = validateSignalTick(tick);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'id')).toBe(true);
    });

    it('rejects non-array parents', () => {
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-123',
        sequence: 1,
        tick: 1,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: 'not-array',
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };

      const result = validateSignalTick(tick);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'parents')).toBe(true);
    });

    it('rejects unknown fields in strict mode', () => {
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-123',
        sequence: 1,
        tick: 1,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
        unknownField: 'should error',
      };

      const result = validateSignalTick(tick, { strict: true });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'UNKNOWN_FIELD')).toBe(true);
    });

    it('allows unknown fields in non-strict mode', () => {
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-123',
        sequence: 1,
        tick: 1,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
        unknownField: 'should not error',
      };

      const result = validateSignalTick(tick, { strict: false });
      expect(result.valid).toBe(true);
    });

    it('detects sequence gap in strict mode', () => {
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-123',
        sequence: 10,
        tick: 10,
        timestamp: Date.now(),
        contentHash: 'abc123',
        schemaHash: 'def456',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };

      const result = validateSignalTick(tick, { maxSequence: 5 });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'SEQUENCE_GAP')).toBe(true);
    });
  });

  describe('validateSignalWindow', () => {
    it('validates a correct signal window', () => {
      const window = {
        schemaId: SIGNAL_WINDOW_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'window-123',
        startTick: 1,
        endTick: 10,
        startTime: Date.now() - 1000,
        windowDurationMs: 1000,
        tickCount: 10,
        tickHashes: ['hash1', 'hash2'],
        contentHash: 'abc123',
        schemaHash: 'def456',
        closed: true,
      };

      const result = validateSignalWindow(window);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects endTick before startTick', () => {
      const window = {
        schemaId: SIGNAL_WINDOW_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'window-123',
        startTick: 10,
        endTick: 5,
        startTime: Date.now(),
        windowDurationMs: 1000,
        tickCount: 0,
        tickHashes: [],
        contentHash: 'abc123',
        schemaHash: 'def456',
        closed: false,
      };

      const result = validateSignalWindow(window);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'INVALID_RANGE')).toBe(true);
    });

    it('rejects empty tickHashes', () => {
      const window = {
        schemaId: SIGNAL_WINDOW_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'window-123',
        startTick: 1,
        endTick: 10,
        startTime: Date.now(),
        windowDurationMs: 1000,
        tickCount: 10,
        tickHashes: 'not-array',
        contentHash: 'abc123',
        schemaHash: 'def456',
        closed: true,
      };

      const result = validateSignalWindow(window);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'tickHashes')).toBe(true);
    });
  });

  describe('generateSignalTickSchemaHash', () => {
    it('generates consistent hash', () => {
      const hash1 = generateSignalTickSchemaHash();
      const hash2 = generateSignalTickSchemaHash();
      expect(hash1).toBe(hash2);
    });

    it('generates non-empty hash', () => {
      const hash = generateSignalTickSchemaHash();
      expect(hash.length).toBeGreaterThan(0);
    });
  });

  describe('generateSignalWindowSchemaHash', () => {
    it('generates consistent hash', () => {
      const hash1 = generateSignalWindowSchemaHash();
      const hash2 = generateSignalWindowSchemaHash();
      expect(hash1).toBe(hash2);
    });
  });
});

describe('signalProcessor', () => {
  describe('BackpressureController', () => {
    it('allows acceptance when below high water mark', () => {
      const controller = new BackpressureController();
      expect(controller.canAccept()).toBe(true);
    });

    it('blocks acceptance at max queue size', () => {
      const controller = new BackpressureController({ maxQueueSize: 1 });
      controller.accept();
      expect(controller.canAccept()).toBe(false);
    });

    it('resumes when queue drops below low water mark', () => {
      const controller = new BackpressureController({
        maxQueueSize: 10,
        highWaterMark: 8,
        lowWaterMark: 2,
      });
      
      // Fill to high water mark
      for (let i = 0; i < 8; i++) {
        controller.accept();
      }
      expect(controller.canAccept()).toBe(false);
      
      // Drain to below low water mark (queueSize = 8 - 7 = 1 < 2)
      for (let i = 0; i < 7; i++) {
        controller.complete();
      }
      expect(controller.canAccept()).toBe(true);
    });

    it('calculates correct load factor', () => {
      const controller = new BackpressureController({ maxQueueSize: 100 });
      controller.accept();
      controller.accept();
      expect(controller.getLoadFactor()).toBe(0.02);
    });

    it('detects high water mark', () => {
      const controller = new BackpressureController({
        maxQueueSize: 100,
        highWaterMark: 50,
      });
      
      for (let i = 0; i < 50; i++) {
        controller.accept();
      }
      
      expect(controller.isHighWaterMark()).toBe(true);
    });

    it('does not go negative on complete', () => {
      const controller = new BackpressureController();
      controller.complete();
      expect(controller.getState().queueSize).toBe(0);
    });
  });

  describe('ReplayParityValidator', () => {
    it('validates identical replay', () => {
      const validator = new ReplayParityValidator();
      
      const original = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-1',
        sequence: 1,
        tick: 1,
        timestamp: 1000,
        contentHash: 'hash1',
        schemaHash: 'schema1',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };
      
      const replay = { ...original };
      
      validator.registerOriginal(original);
      validator.registerReplay(replay);
      
      const result = validator.validate();
      expect(result.parity).toBe(true);
      expect(result.mismatches).toHaveLength(0);
    });

    it('detects content hash mismatch', () => {
      const validator = new ReplayParityValidator();
      
      const original = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-1',
        sequence: 1,
        tick: 1,
        timestamp: 1000,
        contentHash: 'hash1',
        schemaHash: 'schema1',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };
      
      const replay = { ...original, contentHash: 'different' };
      
      validator.registerOriginal(original);
      validator.registerReplay(replay);
      
      const result = validator.validate();
      expect(result.parity).toBe(false);
      expect(result.mismatches.some(m => m.field === 'contentHash')).toBe(true);
    });

    it('detects missing replay', () => {
      const validator = new ReplayParityValidator();
      
      const original = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-1',
        sequence: 1,
        tick: 1,
        timestamp: 1000,
        contentHash: 'hash1',
        schemaHash: 'schema1',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };
      
      validator.registerOriginal(original);
      // No replay registered
      
      const result = validator.validate();
      expect(result.parity).toBe(false);
      expect(result.drift).toBe(1);
    });

    it('clears state', () => {
      const validator = new ReplayParityValidator();
      
      const tick = {
        schemaId: SIGNAL_TICK_SCHEMA_ID,
        schemaVersion: 'v1',
        id: 'tick-1',
        sequence: 1,
        tick: 1,
        timestamp: 1000,
        contentHash: 'hash1',
        schemaHash: 'schema1',
        parents: [],
        windowId: 'window-1',
        isCheckpoint: false,
        retryCount: 0,
      };
      
      validator.registerOriginal(tick);
      validator.clear();
      
      const result = validator.validate();
      expect(result.parity).toBe(true);
      expect(result.replayedTicks).toBe(0);
    });
  });

  describe('createSignalTick', () => {
    it('creates a valid tick', () => {
      const payload = { data: 'test' };
      const tick = createSignalTick(payload, { windowId: 'window-1' });
      
      expect(tick.schemaId).toBe(SIGNAL_TICK_SCHEMA_ID);
      expect(tick.schemaVersion).toBe('v1');
      expect(tick.windowId).toBe('window-1');
      expect(tick.isCheckpoint).toBe(false);
      expect(tick.retryCount).toBe(0);
      expect(tick.parents).toEqual([]);
    });

    it('uses provided id', () => {
      const tick = createSignalTick({ data: 'test' }, { windowId: 'window-1', id: 'custom-id' });
      expect(tick.id).toBe('custom-id');
    });

    it('sets checkpoint flag', () => {
      const tick = createSignalTick({ data: 'test' }, { windowId: 'window-1', isCheckpoint: true });
      expect(tick.isCheckpoint).toBe(true);
    });

    it('sets parent ids', () => {
      const tick = createSignalTick({ data: 'test' }, { windowId: 'window-1', parentIds: ['parent-1', 'parent-2'] });
      expect(tick.parents).toEqual(['parent-1', 'parent-2']);
    });
  });

  describe('BoundedSignalIterator', () => {
    it('iterates over ticks', async () => {
      const ticks: any[] = [];
      
      for (let i = 0; i < 3; i++) {
        ticks.push({
          schemaId: SIGNAL_TICK_SCHEMA_ID,
          schemaVersion: 'v1',
          id: `tick-${i}`,
          sequence: i + 1,
          tick: i + 1,
          timestamp: Date.now(),
          contentHash: `hash-${i}`,
          schemaHash: 'schema',
          parents: [],
          windowId: 'window-1',
          isCheckpoint: false,
          retryCount: 0,
        });
      }
      
      const asyncIterable = {
        [Symbol.asyncIterator]: async function* () {
          for (const tick of ticks) {
            yield tick;
          }
        },
      };
      
      const iterator = new BoundedSignalIterator(asyncIterable, {
        windowDurationMs: 60000,
        maxTicksPerWindow: 10,
      });
      
      const batches: any[] = [];
      for await (const batch of iterator) {
        batches.push(batch);
      }
      
      expect(batches.length).toBeGreaterThan(0);
    });
  });
});
