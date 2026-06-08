import { describe, expect, it } from 'vitest';
import { makeVisiblePatch, patchIsSafe } from './visiblePatch';

describe('visiblePatch', () => {
  it('accepts non-empty editor text', () => {
    expect(patchIsSafe(makeVisiblePatch('a.ts', 'export const ok = true;'))).toBe(true);
  });

  it('blocks conflict marker text', () => {
    const marker = '<' + '<' + '<' + '<' + '<' + '<' + '<';
    expect(patchIsSafe(makeVisiblePatch('a.ts', marker))).toBe(false);
  });
});
