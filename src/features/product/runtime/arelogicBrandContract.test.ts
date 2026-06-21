import { describe, expect, it } from 'vitest';

import {
  ARELOGIC_BRAND_CLASSES,
  ARELOGIC_BRAND_PRIORITY,
  ARELOGIC_BRAND_TOKENS,
  assertArelogicBrandContractValid,
  validateArelogicBrandContract,
} from './arelogicBrandContract';

describe('ARELogic brand contract', () => {
  it('keeps the bundled ARELogic brand contract valid', () => {
    const report = validateArelogicBrandContract();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
    expect(() => assertArelogicBrandContractValid()).not.toThrow();
  });

  it('keeps brand visuals behind runtime, accessibility and component contracts', () => {
    expect(ARELOGIC_BRAND_PRIORITY).toEqual([
      'runtime-contracts',
      'accessibility-contracts',
      'component-contracts',
      'brand-visual-layer',
    ]);
  });

  it('exposes the ARELogic color identity as namespaced tokens', () => {
    const tokenVariables = ARELOGIC_BRAND_TOKENS.map((token) => token.cssVariable);

    expect(tokenVariables).toContain('--are-void');
    expect(tokenVariables).toContain('--are-ion');
    expect(tokenVariables).toContain('--are-matter');
    expect(tokenVariables).toContain('--are-signal');
    expect(tokenVariables).toContain('--are-warn');
    expect(tokenVariables).toContain('--are-danger');

    for (const token of ARELOGIC_BRAND_TOKENS) {
      expect(token.cssVariable.startsWith('--are-')).toBe(true);
      expect(token.value).toMatch(/^#[0-9A-F]{6}$/);
      expect(token.purpose.length).toBeGreaterThan(0);
    }
  });

  it('keeps brand classes namespaced and attached to existing UI contracts', () => {
    for (const brandClass of ARELOGIC_BRAND_CLASSES) {
      expect(brandClass.name.startsWith('arelogic-')).toBe(true);
      expect(brandClass.purpose.length).toBeGreaterThan(0);
      expect(brandClass.attachesTo.length).toBeGreaterThan(0);
    }
  });
});
