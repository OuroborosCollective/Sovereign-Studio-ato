import { describe, expect, it } from 'vitest';
import { describeFreeFirstPlan, freeFirstProviderRoute } from './freeFirstPlan';

describe('freeFirstPlan', () => {
  it('keeps no-key providers first', () => {
    expect(freeFirstProviderRoute[0]).toBe('mlvoca');
    expect(freeFirstProviderRoute[1]).toBe('pollinations');
  });

  it('does not require a key at boot', () => {
    expect(describeFreeFirstPlan().keyRequiredAtBoot).toBe(false);
  });
});
