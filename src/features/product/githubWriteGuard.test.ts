import { describe, expect, it } from 'vitest';
import { canWriteToGitHub, explainWriteGuard } from './githubWriteGuard';

describe('githubWriteGuard', () => {
  it('blocks missing token', () => {
    expect(canWriteToGitHub('', 'a.ts', 'x')).toBe(false);
    expect(explainWriteGuard('', 'a.ts', 'x')).toBe('missing-token');
  });

  it('allows complete write input', () => {
    expect(canWriteToGitHub('12345678901', 'a.ts', 'x')).toBe(true);
    expect(explainWriteGuard('12345678901', 'a.ts', 'x')).toBe('ready');
  });
});
