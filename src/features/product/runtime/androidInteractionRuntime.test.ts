import { describe, expect, it, vi } from 'vitest';
import { buildRepoDetectedHint, isSingleGithubRepoUrl, safeVibrate } from './androidInteractionRuntime';

describe('androidInteractionRuntime', () => {
  it('detects single GitHub repo URLs only', () => {
    expect(isSingleGithubRepoUrl('https://github.com/o/r')).toBe(true);
    expect(isSingleGithubRepoUrl('https://github.com/o/r\nmore')).toBe(false);
    expect(isSingleGithubRepoUrl('hello')).toBe(false);
  });

  it('builds local repo detected hint', () => {
    expect(buildRepoDetectedHint('https://github.com/o/r')).toContain('o/r');
  });

  it('vibrates only when supported', () => {
    const vibrate = vi.fn();
    expect(safeVibrate({ vibrate }, 10)).toBe(true);
    expect(vibrate).toHaveBeenCalledWith(10);
    expect(safeVibrate(undefined, 10)).toBe(false);
  });

  it('returns false when vibrate cannot run', () => {
    const vibrate = vi.fn(() => false);
    expect(safeVibrate({ vibrate }, 10)).toBe(true);
  });
});
