import { describe, expect, it } from 'vitest';
import { describeFreeFirstPlan, freeFirstProviderRoute } from './freeFirstPlan';

describe('freeFirstPlan', () => {
  it('keeps the authenticated backend as the only online route', () => {
    expect(freeFirstProviderRoute).toEqual(['optional-user-keys']);
  });

  it('does not require a key at boot', () => {
    expect(describeFreeFirstPlan().keyRequiredAtBoot).toBe(false);
  });
});
