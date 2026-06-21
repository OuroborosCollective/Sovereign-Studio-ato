import {
  SOVEREIGN_APP_CLASSES,
  SOVEREIGN_TAB_STYLE_CONTRACT,
  type SovereignTabStyleDefinition,
} from './sovereignStyleContract';

export type SovereignComponentState = 'idle' | 'busy' | 'success' | 'warning' | 'error' | 'disabled';

export interface SovereignComponentContract {
  name: string;
  rootClass: string;
  dataRole: string;
  testIdPattern: RegExp;
  requiredAriaLabel: boolean;
  states: readonly SovereignComponentState[];
}

export interface SovereignActionRoleContract {
  primary: 'action-primary';
  secondary: 'action-secondary';
  destructive: 'action-destructive';
  navigation: 'action-navigation';
  diagnostic: 'action-diagnostic';
}

export interface SovereignComponentContractReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export const SOVEREIGN_COMPONENT_STATES = ['idle', 'busy', 'success', 'warning', 'error', 'disabled'] as const;

export const SOVEREIGN_ACTION_ROLES: SovereignActionRoleContract = {
  primary: 'action-primary',
  secondary: 'action-secondary',
  destructive: 'action-destructive',
  navigation: 'action-navigation',
  diagnostic: 'action-diagnostic',
};

export const SOVEREIGN_TEST_ID_PATTERN = /^[a-z][a-z0-9-]*__[a-z][a-z0-9-]*$/;

export const SOVEREIGN_APP_SHELL_CONTRACT: SovereignComponentContract = {
  name: 'SovereignAppShell',
  rootClass: SOVEREIGN_APP_CLASSES.shell,
  dataRole: 'sovereign-app-shell',
  testIdPattern: SOVEREIGN_TEST_ID_PATTERN,
  requiredAriaLabel: false,
  states: ['idle', 'busy', 'error'],
};

export const SOVEREIGN_TABBAR_CONTRACT: SovereignComponentContract = {
  name: 'SovereignTabbar',
  rootClass: SOVEREIGN_APP_CLASSES.tabbar,
  dataRole: 'sovereign-tabbar',
  testIdPattern: SOVEREIGN_TEST_ID_PATTERN,
  requiredAriaLabel: true,
  states: ['idle', 'busy'],
};

export const SOVEREIGN_ACTION_BUTTON_CONTRACT: SovereignComponentContract = {
  name: 'SovereignActionButton',
  rootClass: 'sovereign-action-button',
  dataRole: SOVEREIGN_ACTION_ROLES.primary,
  testIdPattern: SOVEREIGN_TEST_ID_PATTERN,
  requiredAriaLabel: true,
  states: SOVEREIGN_COMPONENT_STATES,
};

export const SOVEREIGN_COMPONENT_CONTRACTS: SovereignComponentContract[] = [
  SOVEREIGN_APP_SHELL_CONTRACT,
  SOVEREIGN_TABBAR_CONTRACT,
  SOVEREIGN_ACTION_BUTTON_CONTRACT,
];

export function createSovereignTestId(context: string, action: string): string {
  const testId = `${context}__${action}`;
  if (!SOVEREIGN_TEST_ID_PATTERN.test(testId)) {
    throw new Error(`Invalid Sovereign test id: ${testId}`);
  }

  return testId;
}

export function getSovereignTabButtonContract(style: SovereignTabStyleDefinition): SovereignComponentContract {
  return {
    name: `SovereignTabButton:${style.tab}`,
    rootClass: style.cssClass,
    dataRole: style.dataRole,
    testIdPattern: SOVEREIGN_TEST_ID_PATTERN,
    requiredAriaLabel: true,
    states: ['idle', 'busy', 'disabled'],
  };
}

function validateComponentContract(contract: SovereignComponentContract): string[] {
  const errors: string[] = [];

  if (!contract.name.trim()) errors.push('Component contract name must not be empty.');
  if (!contract.rootClass.trim()) errors.push(`${contract.name} rootClass must not be empty.`);
  if (!contract.dataRole.trim()) errors.push(`${contract.name} dataRole must not be empty.`);
  if (!contract.testIdPattern.test('sample-context__sample-action')) errors.push(`${contract.name} testIdPattern must accept context__action.`);
  if (contract.testIdPattern.test('sample-context-sample-action')) errors.push(`${contract.name} testIdPattern must reject missing double separator.`);
  if (!contract.states.length) errors.push(`${contract.name} states must not be empty.`);

  for (const state of contract.states) {
    if (!SOVEREIGN_COMPONENT_STATES.includes(state)) errors.push(`${contract.name} has unknown state ${state}.`);
  }

  return errors;
}

export function validateSovereignComponentContracts(): SovereignComponentContractReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const tabContracts = SOVEREIGN_TAB_STYLE_CONTRACT.map(getSovereignTabButtonContract);
  const allContracts = [...SOVEREIGN_COMPONENT_CONTRACTS, ...tabContracts];
  const dataRoles = allContracts.map((contract) => contract.dataRole);

  for (const contract of allContracts) {
    errors.push(...validateComponentContract(contract));
  }

  const duplicateRoles = dataRoles.filter((role, index) => dataRoles.indexOf(role) !== index);
  if (duplicateRoles.length) errors.push(`Duplicate component data-role values: ${Array.from(new Set(duplicateRoles)).join(', ')}.`);

  const visibleTabWithoutAria = tabContracts.filter((contract) => !contract.requiredAriaLabel);
  if (visibleTabWithoutAria.length) errors.push('Every visible tab contract must require aria-label.');

  if (!SOVEREIGN_ACTION_BUTTON_CONTRACT.rootClass.startsWith('sovereign-')) {
    warnings.push('Action button class should use the Sovereign namespace.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} component contract error(s), ${warnings.length} warning(s).`,
  };
}

export function assertSovereignComponentContractsValid(): void {
  const report = validateSovereignComponentContracts();
  if (!report.valid) throw new Error(`Sovereign component contracts invalid: ${report.errors.join(' | ')}`);
}
