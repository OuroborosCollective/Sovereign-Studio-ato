import { describe, expect, it } from 'vitest';

import { SOVEREIGN_PRODUCT_TEMPLATE } from './sovereignProductTemplate';
import {
  SOVEREIGN_APP_CLASSES,
  SOVEREIGN_TAB_STYLE_CONTRACT,
  assertSovereignStyleContractValid,
  getSovereignTabStyle,
  validateSovereignStyleContract,
} from './sovereignStyleContract';

describe('sovereign style contract', () => {
  it('keeps the bundled style contract valid', () => {
    const report = validateSovereignStyleContract();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
    expect(() => assertSovereignStyleContractValid()).not.toThrow();
  });

  it('covers every product template tab with stable UI metadata', () => {
    const templateTabs = SOVEREIGN_PRODUCT_TEMPLATE.tabs.map((tab) => tab.id);
    const styledTabs = SOVEREIGN_TAB_STYLE_CONTRACT.map((style) => style.tab);

    expect(styledTabs).toEqual(templateTabs);

    for (const tab of templateTabs) {
      const style = getSovereignTabStyle(tab);

      expect(style.cssClass).toContain(SOVEREIGN_APP_CLASSES.tab);
      expect(style.cssClass).toContain(`sovereign-tab-${tab}`);
      expect(style.activeCssClass).toBe(SOVEREIGN_APP_CLASSES.activeTab);
      expect(style.dataRole).toBe(`sovereign-tab-${tab}`);
      expect(style.ariaLabel.length).toBeGreaterThan(0);
      expect(Number.isInteger(style.mobilePriority)).toBe(true);
    }
  });

  it('keeps the Android primary tabs first and in product order', () => {
    const priorities = SOVEREIGN_PRODUCT_TEMPLATE.primaryFlow.map((tab) => getSovereignTabStyle(tab).mobilePriority);

    expect(priorities).toEqual([0, 1, 2, 3]);
  });

  it('keeps data roles unique for automation and mobile tests', () => {
    const roles = SOVEREIGN_TAB_STYLE_CONTRACT.map((style) => style.dataRole);

    expect(new Set(roles).size).toBe(roles.length);
  });
});
