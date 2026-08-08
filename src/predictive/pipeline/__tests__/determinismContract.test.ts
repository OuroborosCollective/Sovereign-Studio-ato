import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { DETERMINISTIC_ITERABLE_ALLOWLIST } from '../deterministicIterables';

const PIPELINE_DIR = resolve(__dirname, '..');
const PIPELINE_FILES = [
  'deterministicIterables.ts',
  'signalOrdering.ts',
  'tickWindow.ts',
  'featureExtraction.ts',
  'signalPipeline.ts',
  'index.ts',
];

/**
 * Issue #1170 contract: the deterministic signal pipeline MUST NOT depend on
 * wall-clock time, randomness, or other non-deterministic primitives. Any such
 * import would break replay parity silently. This test pins the allowlist.
 */
describe('deterministic signal pipeline - non-determinism contract', () => {
  it('pipeline source files contain no Date.now / Math.random / new Date references', () => {
    for (const file of PIPELINE_FILES) {
      const src = readFileSync(resolve(PIPELINE_DIR, file), 'utf8');
      expect(src, `${file} must not use Date.now`).not.toMatch(/\bDate\.now\b/);
      expect(src, `${file} must not use Math.random`).not.toMatch(/\bMath\.random\b/);
      expect(src, `${file} must not construct new Date()`).not.toMatch(/new\s+Date\s*\(/);
      expect(src, `${file} must not use performance.now`).not.toMatch(/\bperformance\.now\b/);
    }
  });

  it('pipeline source files do not import forbidden modules', () => {
    for (const file of PIPELINE_FILES) {
      const src = readFileSync(resolve(PIPELINE_DIR, file), 'utf8');
      expect(src, `${file} must not call getRandomValues`).not.toMatch(/getRandomValues/);
      expect(src, `${file} must not call randomUUID`).not.toMatch(/randomUUID/);
    }
  });

  it('deterministicIterables exports only the allowlisted native primitives', () => {
    expect([...DETERMINISTIC_ITERABLE_ALLOWLIST].sort()).toEqual(
      [
        'chunkwise',
        'chunkwiseOverlap',
        'pairwise',
        'zipEqual',
        'groupBy',
        'runningDifference',
        'runningTotal',
        'toMinMax',
      ].sort(),
    );
  });

  it('the public pipeline barrel does not re-export iterable primitives by wildcard', () => {
    const src = readFileSync(resolve(PIPELINE_DIR, 'index.ts'), 'utf8');
    expect(src).toMatch(/DETERMINISTIC_ITERABLE_ALLOWLIST/);
    expect(src).not.toMatch(/chunkwise,/);
    expect(src).not.toMatch(/chunkwiseOverlap,/);
  });
});
