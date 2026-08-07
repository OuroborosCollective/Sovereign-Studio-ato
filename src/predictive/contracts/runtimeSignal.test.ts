/**
 * Runtime Signal Contract Tests
 *
 * @module predictive/contracts/runtimeSignal.test
 */

import { describe, it, expect } from 'vitest';
import {
  validateSignal,
  validateSignalWindow,
  generateSchemaHash,
  generateSignalHash,
  createSchemaMetadata,
  validateSignalPayloadSize,
  validateWindowPayloadSize,
  SIGNAL_MAX_METADATA_SIZE,
  SIGNAL_WINDOW_MAX_SIGNALS,
  RUNTIME_SIGNAL_SCHEMA_ID,
  RUNTIME_SIGNAL_SCHEMA_VERSION,
  SignalErrorCode,
} from './runtimeSignal';

describe('RuntimeSignal Contract', () => {
  describe('validateSignal', () => {
    it('should validate a correct signal', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
      };

      const result = validateSignal(signal);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.schemaId).toBe(RUNTIME_SIGNAL_SCHEMA_ID);
    });

    it('should reject null input', () => {
      const result = validateSignal(null);
      expect(result.valid).toBe(false);
      expect(result.errors[0].code).toBe(SignalErrorCode.INVALID_TYPE);
    });

    it('should reject non-object input', () => {
      const result = validateSignal('string');
      expect(result.valid).toBe(false);
    });

    it('should reject missing required fields', () => {
      const result = validateSignal({ id: 'sig-001' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === SignalErrorCode.MISSING_REQUIRED)).toBe(true);
    });

    it('should reject unknown fields in strict mode', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
        unknownField: 'bad',
      };

      const result = validateSignal(signal, { strict: true });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === SignalErrorCode.UNKNOWN_FIELD)).toBe(true);
    });

    it('should allow unknown fields in non-strict mode', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
        unknownField: 'ok',
      };

      const result = validateSignal(signal, { strict: false });
      expect(result.valid).toBe(true);
    });

    it('should reject NaN values', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: NaN,
        timestamp: 1700000000000,
        traceId: 'trace-001',
      };

      const result = validateSignal(signal);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === SignalErrorCode.NON_FINITE_NUMBER)).toBe(true);
    });

    it('should reject Infinity values', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: Infinity,
        timestamp: 1700000000000,
        traceId: 'trace-001',
      };

      const result = validateSignal(signal);
      expect(result.valid).toBe(false);
    });

    it('should reject negative zero values', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: -0,
        timestamp: 1700000000000,
        traceId: 'trace-001',
      };

      const result = validateSignal(signal);
      expect(result.valid).toBe(false);
    });

    it('should reject empty string id', () => {
      const signal = {
        id: '',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
      };

      const result = validateSignal(signal);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'id')).toBe(true);
    });

    it('should reject invalid timestamp', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: -1,
        traceId: 'trace-001',
      };

      const result = validateSignal(signal);
      expect(result.valid).toBe(false);
    });

    it('should accept optional tick and sequence', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
        tick: 100,
        sequence: 5,
      };

      const result = validateSignal(signal);
      expect(result.valid).toBe(true);
    });

    it('should reject non-canonical tick (NaN)', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
        tick: NaN,
      };

      const result = validateSignal(signal);
      expect(result.valid).toBe(false);
    });
  });

  describe('validateSignalWindow', () => {
    it('should validate a correct window', () => {
      const window = {
        windowId: 'win-001',
        signals: [
          {
            id: 'sig-001',
            node: 'runtime.test',
            value: 42.5,
            timestamp: 1700000000000,
            traceId: 'trace-001',
          },
        ],
        startTick: 0,
        endTick: 10,
        configHash: 'abc123',
      };

      const result = validateSignalWindow(window);
      expect(result.valid).toBe(true);
    });

    it('should reject window with invalid signals', () => {
      const window = {
        windowId: 'win-001',
        signals: [
          {
            id: 'sig-001',
            // missing required fields
          },
        ],
        startTick: 0,
        endTick: 10,
        configHash: 'abc123',
      };

      const result = validateSignalWindow(window);
      expect(result.valid).toBe(false);
    });

    it('should reject window with empty windowId', () => {
      const window = {
        windowId: '',
        signals: [],
        startTick: 0,
        endTick: 10,
        configHash: 'abc123',
      };

      const result = validateSignalWindow(window);
      expect(result.valid).toBe(false);
    });
  });

  describe('Schema Hash', () => {
    it('should generate consistent schema hash', () => {
      const hash1 = generateSchemaHash(RUNTIME_SIGNAL_SCHEMA_ID, RUNTIME_SIGNAL_SCHEMA_VERSION);
      const hash2 = generateSchemaHash(RUNTIME_SIGNAL_SCHEMA_ID, RUNTIME_SIGNAL_SCHEMA_VERSION);
      expect(hash1).toBe(hash2);
    });

    it('should generate different hashes for different versions', () => {
      const hash1 = generateSchemaHash(RUNTIME_SIGNAL_SCHEMA_ID, '1.0.0');
      const hash2 = generateSchemaHash(RUNTIME_SIGNAL_SCHEMA_ID, '2.0.0');
      expect(hash1).not.toBe(hash2);
    });

    it('should generate deterministic signal hash', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
        tick: 100,
        sequence: 5,
      };

      const hash1 = generateSignalHash(signal);
      const hash2 = generateSignalHash(signal);
      expect(hash1).toBe(hash2);
    });

    it('should generate different hashes for different signals', () => {
      const signal1 = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
      };

      const signal2 = {
        id: 'sig-002',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
      };

      const hash1 = generateSignalHash(signal1);
      const hash2 = generateSignalHash(signal2);
      expect(hash1).not.toBe(hash2);
    });
  });

  describe('createSchemaMetadata', () => {
    it('should create metadata with defaults', () => {
      const metadata = createSchemaMetadata();
      expect(metadata.schemaId).toBe(RUNTIME_SIGNAL_SCHEMA_ID);
      expect(metadata.schemaVersion).toBe(RUNTIME_SIGNAL_SCHEMA_VERSION);
      expect(metadata.schemaHash).toBeDefined();
    });

    it('should allow overrides', () => {
      const metadata = createSchemaMetadata({ sourceRevision: 'abc123' });
      expect(metadata.sourceRevision).toBe('abc123');
    });
  });

  describe('Payload Size Validation', () => {
    it('should accept small metadata', () => {
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
        metadata: { key: 'value' },
      };

      expect(validateSignalPayloadSize(signal)).toBe(true);
    });

    it('should reject oversized metadata', () => {
      const largeMetadata = { data: 'x'.repeat(SIGNAL_MAX_METADATA_SIZE + 1) };
      const signal = {
        id: 'sig-001',
        node: 'runtime.test',
        value: 42.5,
        timestamp: 1700000000000,
        traceId: 'trace-001',
        metadata: largeMetadata,
      };

      expect(validateSignalPayloadSize(signal)).toBe(false);
    });

    it('should validate window signal count', () => {
      const smallWindow = {
        windowId: 'win-001',
        signals: Array(10).fill({
          id: 'sig-001',
          node: 'runtime.test',
          value: 42.5,
          timestamp: 1700000000000,
          traceId: 'trace-001',
        }),
        startTick: 0,
        endTick: 10,
        configHash: 'abc123',
      };

      expect(validateWindowPayloadSize(smallWindow)).toBe(true);

      const largeWindow = {
        windowId: 'win-002',
        signals: Array(SIGNAL_WINDOW_MAX_SIGNALS + 1).fill({
          id: 'sig-001',
          node: 'runtime.test',
          value: 42.5,
          timestamp: 1700000000000,
          traceId: 'trace-001',
        }),
        startTick: 0,
        endTick: 10,
        configHash: 'abc123',
      };

      expect(validateWindowPayloadSize(largeWindow)).toBe(false);
    });
  });
});
