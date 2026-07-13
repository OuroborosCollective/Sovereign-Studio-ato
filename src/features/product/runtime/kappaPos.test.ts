import { describe, expect, it } from 'vitest';
import {
  KAPPA_ONE,
  KAPPA_ZERO,
  cosineSimilarityKappa,
  decodeKappaVectorLittleEndian,
  encodeKappaVectorLittleEndian,
  fnv1a64Hex,
  integerSqrt,
  kappaFromDecimalString,
  kappaToDecimalString,
  microUsdFromUnits,
  multiplyKappa,
  sha256Hex,
} from './kappaPos';

describe('kappaPos', () => {
  it('parst Dezimaltext ohne IEEE-754-Zwischenschritt', () => {
    expect(kappaFromDecimalString('0.8543219')).toBe(854_321n);
    expect(kappaFromDecimalString('0.000001')).toBe(1n);
    expect(kappaFromDecimalString('1.000000')).toBe(KAPPA_ONE);
    expect(kappaToDecimalString(kappaFromDecimalString('0.5'))).toBe('0.500000');
    expect(() => kappaFromDecimalString('1.000001')).toThrow(RangeError);
    expect(() => kappaFromDecimalString('1e-6')).toThrow(TypeError);
  });

  it('berechnet Multiplikation und Quadratwurzel ausschließlich mit BigInt', () => {
    expect(multiplyKappa(kappaFromDecimalString('0.5'), kappaFromDecimalString('0.5'))).toBe(250_000n);
    expect(integerSqrt(0n)).toBe(0n);
    expect(integerSqrt(15n)).toBe(3n);
    expect(integerSqrt(16n)).toBe(4n);
    expect(integerSqrt(10n ** 30n)).toBe(10n ** 15n);
    expect(() => integerSqrt(-1n)).toThrow(RangeError);
  });

  it('liefert deterministische Kappa-Kosinuswerte', () => {
    const unitX = [KAPPA_ONE, KAPPA_ZERO] as const;
    const unitY = [KAPPA_ZERO, KAPPA_ONE] as const;
    const diagonal = [KAPPA_ONE, KAPPA_ONE] as const;

    expect(cosineSimilarityKappa(unitX, unitX)).toBe(KAPPA_ONE);
    expect(cosineSimilarityKappa(unitX, unitY)).toBe(KAPPA_ZERO);
    expect(cosineSimilarityKappa(unitX, diagonal)).toBe(707_106n);
  });

  it('kodiert Vektoren kanonisch Little-Endian und dekodiert sie verlustfrei', async () => {
    const values = [
      KAPPA_ZERO,
      kappaFromDecimalString('0.5'),
      KAPPA_ONE,
    ] as const;
    const encoded = encodeKappaVectorLittleEndian(values);

    expect(Array.from(encoded.slice(0, 4))).toEqual([0x4b, 0x50, 0x4f, 0x53]);
    expect(Array.from(encoded.slice(4, 16))).toEqual([
      0x01, 0x00,
      0x10, 0x00,
      0x40, 0x42, 0x0f, 0x00,
      0x03, 0x00, 0x00, 0x00,
    ]);
    expect(decodeKappaVectorLittleEndian(encoded)).toEqual(values);
    expect(fnv1a64Hex(encoded)).toHaveLength(16);
    expect(await sha256Hex(encoded)).toBe(
      '728abc2a66dc6f496da448bd3926306ed2758560f52d0357b46c17e327264456',
    );
  });

  it('brandet MicroUsd ohne Number-Konvertierung', () => {
    expect(microUsdFromUnits(12_345_678n)).toBe(12_345_678n);
    expect(() => microUsdFromUnits(-1n)).toThrow(RangeError);
  });
});
