/**
 * Hard Invariant Channel - Unit Tests
 *
 * @module predictive/inference/hardInvariantChannel.test
 */

import { describe, it, expect } from 'vitest';
import {
  checkHardInvariant,
  createHardInvariantReceipt,
  runHardInvariantChannel,
  createDefaultRuntimeInvariantConfig,
  type HardInvariant,
} from './hardInvariantChannel';
import type { RevisionBinding } from './types';

describe('predictive/inference/hardInvariantChannel', () => {
  const mockRevisionBinding: RevisionBinding = {
    runtimeRevision: 'abc1234',
    configRevision: 'cfg_v1',
    schemaVersion: '1.0',
    boundAt: Date.now(),
  };

  describe('checkHardInvariant', () => {
    it('returns passed=true when value is within bounds', () => {
      const invariant: HardInvariant = {
        id: 'test_cpu',
        name: 'CPU Usage',
        category: 'resource',
        currentValue: 50,
        hardMax: 95,
        warningThreshold: 80,
        unit: '%',
        measuredAt: Date.now(),
      };

      const result = checkHardInvariant(invariant, 'any_rev');

      expect(result.passed).toBe(true);
      expect(result.severity).toBe('info');
      expect(result.score).toBe(1.0);
      expect(result.thresholdDistance).toBe(0);
    });

    it('returns passed=false when value exceeds hardMax', () => {
      const invariant: HardInvariant = {
        id: 'test_cpu',
        name: 'CPU Usage',
        category: 'resource',
        currentValue: 97,
        hardMax: 95,
        unit: '%',
        measuredAt: Date.now(),
      };

      const result = checkHardInvariant(invariant, 'any_rev');

      expect(result.passed).toBe(false);
      expect(result.severity).toBe('critical');
      expect(result.score).toBe(0.0);
      expect(result.bound).toBe('max');
      expect(result.thresholdDistance).toBe(2);
    });

    it('returns warning when value exceeds warningThreshold but not hardMax', () => {
      const invariant: HardInvariant = {
        id: 'test_cpu',
        name: 'CPU Usage',
        category: 'resource',
        currentValue: 85,
        hardMax: 95,
        warningThreshold: 80,
        unit: '%',
        measuredAt: Date.now(),
      };

      const result = checkHardInvariant(invariant, 'any_rev');

      expect(result.passed).toBe(true);
      expect(result.severity).toBe('warning');
      expect(result.thresholdDistance).toBe(5);
    });

    it('returns passed=false when value falls below hardMin', () => {
      const invariant: HardInvariant = {
        id: 'test_memory',
        name: 'Memory Available',
        category: 'resource',
        currentValue: 5,
        hardMin: 10,
        unit: '%',
        measuredAt: Date.now(),
      };

      const result = checkHardInvariant(invariant, 'any_rev');

      expect(result.passed).toBe(false);
      expect(result.severity).toBe('critical');
      expect(result.bound).toBe('min');
      expect(result.thresholdDistance).toBe(5);
    });

    it('returns info severity when no bounds defined', () => {
      const invariant: HardInvariant = {
        id: 'test_unknown',
        name: 'Unknown Metric',
        category: 'resource',
        currentValue: 100,
        unit: 'units',
        measuredAt: Date.now(),
      };

      const result = checkHardInvariant(invariant, 'any_rev');

      expect(result.passed).toBe(true);
      expect(result.severity).toBe('info');
      expect(result.bound).toBe('none');
    });

    it('includes correct channel type in result', () => {
      const invariant: HardInvariant = {
        id: 'test',
        name: 'Test',
        category: 'latency',
        currentValue: 100,
        hardMax: 500,
        unit: 'ms',
        measuredAt: Date.now(),
      };

      const result = checkHardInvariant(invariant, 'any_rev');

      expect(result.channelType).toBe('hard_invariant');
      expect(result.category).toBe('latency');
    });
  });

  describe('createHardInvariantReceipt', () => {
    it('creates receipt with deterministic calibration', () => {
      const invariant: HardInvariant = {
        id: 'test',
        name: 'Test',
        category: 'resource',
        currentValue: 50,
        hardMax: 100,
        unit: '%',
        measuredAt: Date.now(),
      };

      const checkResult = checkHardInvariant(invariant, 'any_rev');
      const inputWindowHash = {
        hash: 'test_window',
        signalCount: 1,
        windowStart: Date.now() - 1000,
        windowEnd: Date.now(),
        featureHash: 'test_feat',
      };

      const receipt = createHardInvariantReceipt(
        checkResult,
        mockRevisionBinding,
        inputWindowHash,
        [invariant],
      );

      expect(receipt.schemaVersion).toBe('model-receipt.v1');
      expect(receipt.channelType).toBe('hard_invariant');
      expect(receipt.modelClass).toBe('hard_invariant_deterministic');
      expect(receipt.calibrationMetadata?.method).toBe('deterministic');
      expect(receipt.calibrationMetadata?.score).toBe(1.0);
      expect(receipt.receiptHash).toBeTruthy();
    });

    it('documents unbounded invariants as limitations', () => {
      const boundedInvariant: HardInvariant = {
        id: 'bounded',
        name: 'Bounded',
        category: 'resource',
        currentValue: 50,
        hardMax: 100,
        unit: '%',
        measuredAt: Date.now(),
      };

      const unboundedInvariant: HardInvariant = {
        id: 'unbounded',
        name: 'Unbounded',
        category: 'resource',
        currentValue: 100,
        unit: 'units',
        measuredAt: Date.now(),
      };

      const checkResult = checkHardInvariant(boundedInvariant, 'any_rev');
      const inputWindowHash = {
        hash: 'test',
        signalCount: 2,
        windowStart: Date.now(),
        windowEnd: Date.now(),
        featureHash: 'test',
      };

      const receipt = createHardInvariantReceipt(
        checkResult,
        mockRevisionBinding,
        inputWindowHash,
        [boundedInvariant, unboundedInvariant],
      );

      expect(receipt.knownLimitations).toContain('Unbounded has no defined bounds');
    });
  });

  describe('runHardInvariantChannel', () => {
    it('returns empty array when disabled', () => {
      const config = createDefaultRuntimeInvariantConfig();
      config.enabled = false;

      const results = runHardInvariantChannel(config, mockRevisionBinding, 'test_trace');

      expect(results).toHaveLength(0);
    });

    it('runs channel and produces results for each invariant', () => {
      const config = createDefaultRuntimeInvariantConfig();
      config.invariants = [
        {
          id: 'test1',
          name: 'Test 1',
          category: 'resource',
          currentValue: 50,
          hardMax: 100,
          unit: '%',
          measuredAt: Date.now(),
        },
        {
          id: 'test2',
          name: 'Test 2',
          category: 'latency',
          currentValue: 100,
          hardMax: 500,
          unit: 'ms',
          measuredAt: Date.now(),
        },
      ];

      const results = runHardInvariantChannel(config, mockRevisionBinding, 'test_trace');

      expect(results).toHaveLength(2);
      expect(results[0].channelType).toBe('hard_invariant');
      expect(results[1].channelType).toBe('hard_invariant');
      expect(results[0].receipt.schemaVersion).toBe('model-receipt.v1');
    });

    it('marks passed invariants correctly', () => {
      const config = createDefaultRuntimeInvariantConfig();
      config.invariants = [
        {
          id: 'good',
          name: 'Good Metric',
          category: 'resource',
          currentValue: 50,
          hardMax: 100,
          unit: '%',
          measuredAt: Date.now(),
        },
      ];

      const results = runHardInvariantChannel(config, mockRevisionBinding, 'test_trace');

      expect(results[0].passed).toBe(true);
      expect(results[0].requiresLiveRevalidation).toBe(false);
    });

    it('marks failed invariants and requires revalidation', () => {
      const config = createDefaultRuntimeInvariantConfig();
      config.invariants = [
        {
          id: 'bad',
          name: 'Bad Metric',
          category: 'resource',
          currentValue: 150,
          hardMax: 100,
          unit: '%',
          measuredAt: Date.now(),
        },
      ];

      const results = runHardInvariantChannel(config, mockRevisionBinding, 'test_trace');

      expect(results[0].passed).toBe(false);
      expect(results[0].requiresLiveRevalidation).toBe(true);
      expect(results[0].severity).toBe('critical');
    });
  });

  describe('createDefaultRuntimeInvariantConfig', () => {
    it('creates config with expected runtime invariants', () => {
      const config = createDefaultRuntimeInvariantConfig();

      expect(config.channelType).toBe('hard_invariant');
      expect(config.enabled).toBe(true);
      expect(config.invariants.length).toBe(5); // cpu, memory, error_rate, latency, queue

      const invariantIds = config.invariants.map(i => i.id);
      expect(invariantIds).toContain('cpu_usage');
      expect(invariantIds).toContain('memory_usage');
      expect(invariantIds).toContain('error_rate');
      expect(invariantIds).toContain('latency_p99');
      expect(invariantIds).toContain('queue_depth');
    });

    it('has appropriate thresholds', () => {
      const config = createDefaultRuntimeInvariantConfig();

      const cpuInvariant = config.invariants.find(i => i.id === 'cpu_usage');
      expect(cpuInvariant?.hardMax).toBe(95);
      expect(cpuInvariant?.warningThreshold).toBe(80);

      const latencyInvariant = config.invariants.find(i => i.id === 'latency_p99');
      expect(latencyInvariant?.hardMax).toBe(5000);
      expect(latencyInvariant?.warningThreshold).toBe(2000);
    });
  });
});
