import { describe, expect, it } from 'vitest';

import { SOVEREIGN_PRODUCT_TEMPLATE } from './sovereignProductTemplate';
import {
  SOVEREIGN_ACTION_BUTTON_CONTRACT,
  SOVEREIGN_APP_SHELL_CONTRACT,
  SOVEREIGN_COMPONENT_CONTRACTS,
  SOVEREIGN_TABBAR_CONTRACT,
  createSovereignTestId,
  getSovereignTabButtonContract,
  validateSovereignComponentContracts,
} from './sovereignComponentContracts';
import { SOVEREIGN_TAB_STYLE_CONTRACT } from './sovereignStyleContract';

describe('sovereign component contracts', () => {
  it('keeps the bundled component contracts valid', () => {
    const report = validateSovereignComponentContracts();

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
  });

  it('defines app shell, tabbar and action button as stable contract targets', () => {
    expect(SOVEREIGN_APP_SHELL_CONTRACT.rootClass).toBe('sovereign-app-shell');
    expect(SOVEREIGN_APP_SHELL_CONTRACT.dataRole).toBe('sovereign-app-shell');
    expect(SOVEREIGN_TABBAR_CONTRACT.rootClass).toBe('sovereign-tabbar');
    expect(SOVEREIGN_TABBAR_CONTRACT.requiredAriaLabel).toBe(true);
    expect(SOVEREIGN_ACTION_BUTTON_CONTRACT.rootClass).toBe('sovereign-action-button');
    expect(SOVEREIGN_ACTION_BUTTON_CONTRACT.requiredAriaLabel).toBe(true);
  });

  it('requires the project test id pattern context__action', () => {
    expect(createSovereignTestId('repo', 'load')).toBe('repo__load');
    expect(createSovereignTestId('tabbar', 'repo')).toBe('tabbar__repo');
    expect(() => createSovereignTestId('Repo', 'Load')).toThrow();
    expect(() => createSovereignTestId('repo', 'load_now')).toThrow();
  });

  it('creates a tab button contract for every product template tab', () => {
    const tabContracts = SOVEREIGN_TAB_STYLE_CONTRACT.map(getSovereignTabButtonContract);
    const contractTabs = tabContracts.map((contract) => contract.name.replace('SovereignTabButton:', ''));
    const templateTabs = SOVEREIGN_PRODUCT_TEMPLATE.tabs.map((tab) => tab.id);

    expect(contractTabs).toEqual(templateTabs);

    for (const contract of tabContracts) {
      expect(contract.requiredAriaLabel).toBe(true);
      expect(contract.rootClass).toContain('sovereign-tab');
      expect(contract.dataRole).toMatch(/^sovereign-tab-/);
      expect(contract.testIdPattern.test('tabbar__repo')).toBe(true);
    }
  });

  it('keeps base component data roles unique', () => {
    const roles = SOVEREIGN_COMPONENT_CONTRACTS.map((contract) => contract.dataRole);

    expect(new Set(roles).size).toBe(roles.length);
  });
});
