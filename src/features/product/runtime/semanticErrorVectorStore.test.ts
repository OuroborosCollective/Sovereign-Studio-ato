import { describe, expect, it, vi } from 'vitest';
import { KAPPA_ONE, KAPPA_ZERO } from './kappaPos';
import {
  classifyErrorFamiliesTopN,
  classifyErrorFamily,
  exportVectorStore,
  exportVectorStoreBinary,
  hashVectorStoreSha256,
} from './semanticErrorVectorStore';

describe('semanticErrorVectorStore', () => {
  it('klassifiziert reproduzierbar ohne Zeit- oder Zufallsquelle', () => {
    const dateSpy = vi.spyOn(Date, 'now').mockImplementation(() => {
      throw new Error('Date.now darf im Wahrheitspfad nicht verwendet werden.');
    });
    const randomSpy = vi.spyOn(Math, 'random').mockImplementation(() => {
      throw new Error('Math.random darf im Wahrheitspfad nicht verwendet werden.');
    });

    try {
      const input = '401 unauthorized invalid_token: authentication failed';
      const first = classifyErrorFamily(input);
      const second = classifyErrorFamily(input);

      expect(first).toEqual(second);
      expect(first.family).toBe('GithubAuthError');
      expect(first.traceId).toMatch(/^err-[0-9a-f]{16}$/);
      expect(typeof first.confidence).toBe('bigint');
      expect(first.confidence).toBeGreaterThan(KAPPA_ZERO);
      expect(first.confidence).toBeLessThanOrEqual(KAPPA_ONE);
      expect(first.distance).toBeGreaterThanOrEqual(KAPPA_ZERO);
      expect(first.distance).toBeLessThanOrEqual(KAPPA_ONE);
    } finally {
      dateSpy.mockRestore();
      randomSpy.mockRestore();
    }
  });

  it('bezieht den Stack in Keyword-Erkennung und deterministische Trace-ID ein', () => {
    const result = classifyErrorFamily(
      'request failed',
      'socket_hang_up econnrefused timeout',
    );

    expect(result.family).toBe('GithubNetworkError');
    expect(result.traceId).toBe(
      classifyErrorFamily(
        'request failed',
        'socket_hang_up econnrefused timeout',
      ).traceId,
    );
  });

  it('liefert Top-N stabil und validiert die ganzzahlige Grenze', () => {
    const input = '403 forbidden 403_forbidden rate_limit quota provider_quota_exceeded';
    const first = classifyErrorFamiliesTopN(input, undefined, 3);
    const second = classifyErrorFamiliesTopN(input, undefined, 3);

    expect(first).toEqual(second);
    expect(first).toHaveLength(3);
    expect(first[0].confidence).toBeGreaterThanOrEqual(first[1].confidence);
    expect(classifyErrorFamiliesTopN(input, undefined, 0)).toEqual([]);
    expect(classifyErrorFamiliesTopN(input, undefined, 1.5)).toEqual([]);
  });

  it('exportiert keine verknüpften, mutierbaren internen Arrays', () => {
    const first = exportVectorStore();
    const originalKeyword = first[0].keywords[0];
    const originalValue = first[0].vector[0];

    (first[0].keywords as string[])[0] = 'mutated';
    (first[0].vector as bigint[])[0] = 0n;

    const second = exportVectorStore();
    expect(second[0].keywords[0]).toBe(originalKeyword);
    expect(second[0].vector[0]).toBe(originalValue);
  });

  it('erzeugt bit-identische kanonische Datensätze und einen stabilen SHA-256', async () => {
    const first = exportVectorStoreBinary();
    const second = exportVectorStoreBinary();

    expect(first.map((record) => record.family)).toEqual(
      second.map((record) => record.family),
    );
    expect(first.map((record) => record.fnv1a64)).toEqual(
      second.map((record) => record.fnv1a64),
    );
    expect(first.every((record) => record.payload.byteLength > 16)).toBe(true);

    const firstHash = await hashVectorStoreSha256();
    const secondHash = await hashVectorStoreSha256();
    expect(firstHash).toBe(secondHash);
    expect(firstHash).toMatch(/^[0-9a-f]{64}$/);
  });
});
