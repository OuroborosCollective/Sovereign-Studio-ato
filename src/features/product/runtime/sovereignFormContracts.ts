/**
 * Sovereign Form Contracts
 *
 * Defines authoritative form/input/textarea/select contracts for the Sovereign Studio.
 * These contracts are the single source of truth for form field metadata including
 * accessibility attributes, test identifiers, and sensitive field handling.
 */

export type FormFieldInputType = 'text' | 'url' | 'password' | 'email' | 'number' | 'textarea' | 'select';

export type SovereignFormContractId =
  | 'repo-url'
  | 'repo-branch'
  | 'private-access'
  | 'mission'
  | 'automation-mode';

export interface SovereignFormContract {
  id: SovereignFormContractId;
  label: string;
  dataRole: string;
  testId: string;
  ariaLabel: string;
  inputType: FormFieldInputType;
  autoComplete: string;
  sensitive: boolean;
  required: boolean;
}

export interface SovereignFormContractReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

const FORM_DATA_ROLE_PATTERN = /^(input|textarea|select)-[a-z][a-z0-9-]*$/;
const FORM_TEST_ID_PATTERN = /^[a-z][a-z0-9-]*__[a-z][a-z0-9-]*$/;
const REQUIRED_FORM_IDS: SovereignFormContractId[] = [
  'repo-url',
  'repo-branch',
  'private-access',
  'mission',
  'automation-mode',
];

export const SOVEREIGN_FORM_REPO_URL: SovereignFormContract = {
  id: 'repo-url',
  label: 'GitHub Repository URL',
  dataRole: 'input-repo-url',
  testId: 'repo-url__input',
  ariaLabel: 'GitHub Repository URL',
  inputType: 'url',
  autoComplete: 'url',
  sensitive: false,
  required: true,
};

export const SOVEREIGN_FORM_REPO_BRANCH: SovereignFormContract = {
  id: 'repo-branch',
  label: 'Branch',
  dataRole: 'input-repo-branch',
  testId: 'repo-branch__input',
  ariaLabel: 'Repository branch',
  inputType: 'text',
  autoComplete: 'off',
  sensitive: false,
  required: false,
};

export const SOVEREIGN_FORM_PRIVATE_ACCESS: SovereignFormContract = {
  id: 'private-access',
  label: 'GitHub Private Access',
  dataRole: 'input-private-access',
  testId: 'private-access__input',
  ariaLabel: 'GitHub private access',
  inputType: 'password',
  autoComplete: 'off',
  sensitive: true,
  required: false,
};

export const SOVEREIGN_FORM_MISSION: SovereignFormContract = {
  id: 'mission',
  label: 'Chat Auftrag',
  dataRole: 'textarea-mission',
  testId: 'mission__textarea',
  ariaLabel: 'Sovereign Chat Eingabe',
  inputType: 'textarea',
  autoComplete: 'off',
  sensitive: false,
  required: false,
};

export const SOVEREIGN_FORM_AUTOMATION_MODE: SovereignFormContract = {
  id: 'automation-mode',
  label: 'Automation Mode',
  dataRole: 'select-automation-mode',
  testId: 'automation-mode__select',
  ariaLabel: 'Select automation mode',
  inputType: 'select',
  autoComplete: 'off',
  sensitive: false,
  required: true,
};

export const SOVEREIGN_FORM_CONTRACTS: SovereignFormContract[] = [
  SOVEREIGN_FORM_REPO_URL,
  SOVEREIGN_FORM_REPO_BRANCH,
  SOVEREIGN_FORM_PRIVATE_ACCESS,
  SOVEREIGN_FORM_MISSION,
  SOVEREIGN_FORM_AUTOMATION_MODE,
];

function unique(values: readonly string[]): string[] {
  return Array.from(new Set(values));
}

export function getSovereignFormContract(id: SovereignFormContractId): SovereignFormContract {
  const contract = SOVEREIGN_FORM_CONTRACTS.find((candidate) => candidate.id === id);
  if (!contract) throw new Error(`Unknown Sovereign form contract: ${id}`);
  return contract;
}

export function validateSovereignFormContracts(contracts: SovereignFormContract[] = SOVEREIGN_FORM_CONTRACTS): SovereignFormContractReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const ids = contracts.map((contract) => contract.id);
  const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);

  for (const id of REQUIRED_FORM_IDS) {
    if (!ids.includes(id)) errors.push(`Missing required form contract: ${id}`);
  }

  if (duplicateIds.length) errors.push(`Duplicate form contract ids: ${unique(duplicateIds).join(', ')}`);

  for (const contract of contracts) {
    if (!FORM_DATA_ROLE_PATTERN.test(contract.dataRole)) errors.push(`${contract.id} has invalid dataRole ${contract.dataRole}.`);
    if (!FORM_TEST_ID_PATTERN.test(contract.testId)) errors.push(`${contract.id} has invalid testId ${contract.testId}.`);
    if (!contract.label.trim()) errors.push(`${contract.id} label must not be empty.`);
    if (!contract.ariaLabel.trim()) errors.push(`${contract.id} ariaLabel must not be empty.`);
    if (contract.sensitive && contract.inputType !== 'password') errors.push(`${contract.id} is sensitive and must use password input type.`);
    if (contract.id === 'mission' && contract.inputType !== 'textarea') errors.push('mission contract must use textarea input type.');
  }

  const sensitive = contracts.filter((contract) => contract.sensitive);
  if (!sensitive.length) warnings.push('No sensitive form contracts declared.');

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} form error(s), ${warnings.length} warning(s).`,
  };
}

export function assertSovereignFormContractsValid(contracts: SovereignFormContract[] = SOVEREIGN_FORM_CONTRACTS): void {
  const report = validateSovereignFormContracts(contracts);
  if (!report.valid) throw new Error(`Sovereign form contracts invalid: ${report.errors.join(' | ')}`);
}
