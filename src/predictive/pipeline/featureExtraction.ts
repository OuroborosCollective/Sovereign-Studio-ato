/**
 * Deterministic Feature Extraction.
 *
 * Issue #1170: feature vectors are computed as pure functions of the window's
 * tick values (ordered by tick). The same recorded window always yields the
 * same feature vector and feature hash. No wall-clock, no randomness.
 *
 * @module predictive/pipeline/featureExtraction
 */

import { hashCanonical } from '../inference/hash';
import { runningTotal, toMinMax } from './deterministicIterables';
import type { TickWindow } from './tickWindow';

/** Feature descriptor names bound into the feature receipt. */
export const FEATURE_DESCRIPTOR_NAMES = [
  'sum',
  'mean',
  'min',
  'max',
  'range',
  'firstValue',
  'lastValue',
  'runningTotalVector',
] as const;

export type FeatureDescriptorName = (typeof FEATURE_DESCRIPTOR_NAMES)[number];

export interface FeatureVector {
  /** Descriptor used to derive this vector (e.g. 'sum'). */
  descriptor: FeatureDescriptorName;
  /** The numeric feature vector (causal order). */
  vector: number[];
  /** SHA-256 over the descriptor + canonical vector. */
  featureHash: string;
}

export interface FeatureReceipt {
  /** Window index this receipt was derived from. */
  windowIndex: number;
  /** Hash of the source window (bound to inputs). */
  sourceWindowHash: string;
  /** Descriptor name. */
  descriptor: FeatureDescriptorName;
  /** Feature vector. */
  vector: number[];
  /** Feature content hash. */
  featureHash: string;
}

/**
 * Extract a feature vector for one descriptor from a window's tick values.
 * Values are taken from the signals backing the window, in canonical tick order.
 */
export function extractFeature(
  descriptor: FeatureDescriptorName,
  window: TickWindow,
  values: readonly number[],
): FeatureVector {
  if (values.length === 0) {
    return emptyFeature(descriptor);
  }

  let vector: number[];
  switch (descriptor) {
    case 'sum':
      vector = [values.reduce((a, b) => a + b, 0)];
      break;
    case 'mean':
      vector = [values.reduce((a, b) => a + b, 0) / values.length];
      break;
    case 'min':
    case 'max': {
      const mm = toMinMax(values);
      vector = mm ? [descriptor === 'min' ? mm[0] : mm[1]] : [];
      break;
    }
    case 'range': {
      const mm = toMinMax(values);
      vector = mm ? [mm[1] - mm[0]] : [];
      break;
    }
    case 'firstValue':
      vector = [values[0]];
      break;
    case 'lastValue':
      vector = [values[values.length - 1]];
      break;
    case 'runningTotalVector':
      vector = [...runningTotal(values)];
      break;
    default: {
      // Exhaustiveness guard.
      const _: never = descriptor;
      void _;
      vector = [];
    }
  }

  const featureHash = hashCanonical({ descriptor, vector });
  return { descriptor, vector, featureHash };
}

function emptyFeature(descriptor: FeatureDescriptorName): FeatureVector {
  return { descriptor, vector: [], featureHash: hashCanonical({ descriptor, vector: [] }) };
}

/** Build a feature receipt binding inputs to outputs. */
export function buildFeatureReceipt(
  window: TickWindow,
  values: readonly number[],
  descriptor: FeatureDescriptorName = 'sum',
): FeatureReceipt {
  const feature = extractFeature(descriptor, window, values);
  return {
    windowIndex: window.index,
    sourceWindowHash: window.windowHash,
    descriptor: feature.descriptor,
    vector: feature.vector,
    featureHash: feature.featureHash,
  };
}

/**
 * Verify that a feature receipt is internally consistent: the stored hash must
 * equal a recomputed hash, and the source window hash must match the provided
 * window. Returns the validation result without throwing.
 */
export function verifyFeatureReceipt(
  receipt: FeatureReceipt,
  window: TickWindow,
  values: readonly number[],
): { ok: boolean; recomputedHash: string; sourceMatch: boolean } {
  const recomputed = extractFeature(receipt.descriptor, window, values);
  const sourceMatch = receipt.sourceWindowHash === window.windowHash;
  return {
    ok: recomputed.featureHash === receipt.featureHash && sourceMatch,
    recomputedHash: recomputed.featureHash,
    sourceMatch,
  };
}
