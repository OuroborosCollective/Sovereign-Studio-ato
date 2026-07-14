import { beforeEach, describe, expect, it } from 'vitest';
import { hasUserKeyOverride, invalidateRouteCache } from './useRouteResolver';

describe('hasUserKeyOverride', () => {
  beforeEach(() => {
    invalidateRouteCache();
  });

  it('uses the neutral gemini key contract for override-enabled routes', () => {
    expect(hasUserKeyOverride('chat_standard', { gemini: 'AIza-real-key-shape' })).toBe(true);
    expect(hasUserKeyOverride('chat_standard', { gemini: '   ' })).toBe(false);
  });

  it('does not allow a user key on routes that forbid overrides', () => {
    expect(hasUserKeyOverride('repo_analysis', { gemini: 'AIza-real-key-shape' })).toBe(false);
  });
});
