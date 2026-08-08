import { describe, expect, it } from 'vitest';
import { canonicalJson, hashCanonical, sha256Hex } from './hash';

describe('predictive inference evidence hashing', () => {
  it('matches the published SHA-256 empty-string and abc vectors', () => {
    expect(sha256Hex('')).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    );
    expect(sha256Hex('abc')).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });

  it('canonicalizes object keys without changing array order', () => {
    expect(canonicalJson({ z: 1, a: { d: 4, c: 3 } })).toBe(
      '{"a":{"c":3,"d":4},"z":1}',
    );
    expect(hashCanonical({ a: 1, b: [2, 3] })).toBe(
      hashCanonical({ b: [2, 3], a: 1 }),
    );
    expect(hashCanonical({ a: 1, b: [2, 3] })).not.toBe(
      hashCanonical({ a: 1, b: [3, 2] }),
    );
  });

  it('fails closed for non-finite and unsupported evidence values', () => {
    expect(() => hashCanonical({ score: Number.NaN })).toThrow(TypeError);
    expect(() => hashCanonical({ score: Number.POSITIVE_INFINITY })).toThrow(TypeError);
    expect(() => hashCanonical({ createdAt: new Date() })).toThrow(TypeError);
  });
});
