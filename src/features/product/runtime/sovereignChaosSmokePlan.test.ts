import { describe, expect, it } from 'vitest';
import {
  assertSovereignChaosSmokePlan,
  createSovereignChaosSmokePlan,
  summarizeSovereignChaosSmokePlan,
  type SovereignChaosSmokePlan,
} from './sovereignChaosSmokePlan';

describe('sovereignChaosSmokePlan', () => {
  it('creates a live-safe disabled chaos smoke plan', () => {
    const plan = createSovereignChaosSmokePlan();

    expect(plan.enabledInLivePath).toBe(false);
    expect(plan.steps.length).toBeGreaterThan(0);
    expect(plan.steps.every((step) => step.liveSafe)).toBe(true);
    expect(summarizeSovereignChaosSmokePlan(plan)).toContain('livePath=false');
  });

  it('rejects chaos smoke plans enabled in live path', () => {
    const plan = {
      ...createSovereignChaosSmokePlan(),
      enabledInLivePath: true,
    } as unknown as SovereignChaosSmokePlan;

    expect(() => assertSovereignChaosSmokePlan(plan)).toThrow(/disabled in the live path/i);
  });

  it('rejects steps without expected results', () => {
    const plan = createSovereignChaosSmokePlan();
    const invalid = {
      ...plan,
      steps: [{ ...plan.steps[0], expected: [] }],
    };

    expect(() => assertSovereignChaosSmokePlan(invalid)).toThrow(/expected results/i);
  });
});
