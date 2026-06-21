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

/**
 * Repository URL input field contract.
 */
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

/**
 * Repository branch input field contract.
 */
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

/**
 * Private access input field contract.
 * This field is marked as sensitive and enforces password input type.
 */
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

/**
 * Mission textarea field contract for the builder.
 */
export const SOVEREIGN_FORM_MISSION: SovereignFormContract = {
  id: 'mission',
  label: 'Mission',
  dataRole: 'textarea-mission',
  testId: 'mission__textarea',
  ariaLabel: 'Ideenfabrik Wunschfeld',
  inputType: 'textarea',
  autoComplete: 'off',
  sensitive: false,
  required: false,
};

/**
 * Automation mode select field contract.
 */
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

function unique<T>(values: readonly T[]): T[] {
  return Array.from(new Set(values));
}

export function getSovereignFormContract(id: SovereignFormContractId): SovereignFormContract {
  const contract = SOVEREIGN_FORM_CONTRACTS.find((candidate) => candidate.id === id);
  if (!contract) throw new Error(`Unknown Sovereign form contract: ${id}`);
  return contract;
}

export function validateSovereignFormContracts(): SovereignFormContractReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  const ids = SOVEREIGN_FORM_CONTRACTS.map((contract) => contract.id);
  const dataRoles = SOVEREIGN_FORM_CONTRACTS.map((contract) => contract.dataRole);
  const testIds = SOVEREIGN_FORM_CONTRACTS.map((contract) => contract.testId);

  const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
  const duplicateRoles = dataRoles.filter((role, index) => dataRoles.indexOf(role) !== index);
  const duplicateTestIds = testIds.filter((testId, index) => testIds.indexOf(testId) !== index);

  if (duplicateIds.length) {
    errors.push(`Duplicate form contract ids: ${unique(duplicateIds).join(', ')}.`);
  }
  if (duplicateRoles.length) {
    errors.push(`Duplicate form contract data roles: ${unique(duplicateRoles).join(', ')}.`);
  }
  if (duplicateTestIds.length) {
    errors.push(`Duplicate form contract test ids: ${unique(duplicateTestIds).join(', ')}.`);
  }

  for (const contract of SOVEREIGN_FORM_CONTRACTS) {
    if (!contract.id.trim()) {
      errors.push(`Form contract id must not be empty.`);
    }
    if (!contract.label.trim()) {
      errors.push(`${contract.id}: label must not be empty.`);
    }
    if (!contract.dataRole.trim()) {
      errors.push(`${contract.id}: dataRole must not be empty.`);
    }
    if (!FORM_DATA_ROLE_PATTERN.test(contract.dataRole)) {
      errors.push(`${contract.id}: dataRole must match ${FORM_DATA_ROLE_PATTERN}.`);
    }
    if (!contract.testId.trim()) {
      errors.push(`${contract.id}: testId must not be empty.`);
    }
    if (!FORM_TEST_ID_PATTERN.test(contract.testId)) {
      errors.push(`${contract.id}: testId must match ${FORM_TEST_ID_PATTERN}.`);
    }
    if (!contract.ariaLabel.trim()) {
      errors.push(`${contract.id}: ariaLabel must not be empty.`);
    }
    if (!contract.autoComplete.trim()) {
      errors.push(`${contract.id}: autoComplete must not be empty.`);
    }

    const validInputTypes: FormFieldInputType[] = ['text', 'url', 'password', 'email', 'number', 'textarea', 'select'];
    if (!validInputTypes.includes(contract.inputType)) {
      errors.push(`${contract.id}: unknown input type ${contract.inputType}.`);
    }

    if (contract.sensitive) {
      if (contract.inputType !== 'password') {
        errors.push(`${contract.id}: sensitive field must use inputType 'password'.`);
      }
      if (contract.autoComplete !== 'off') {
        errors.push(`${contract.id}: sensitive field must use autoComplete 'off'.`);
      }
      if (contract.required) {
        warnings.push(`${contract.id}: sensitive field should not be required unless explicitly necessary.`);
      }
    }
  }

  for (const requiredId of REQUIRED_FORM_IDS) {
    if (!ids.includes(requiredId)) {
      errors.push(`Missing required form contract: ${requiredId}.`);
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} form contract error(s), ${warnings.length} warning(s).`,
  };
}

export function assertSovereignFormContractsValid(): void {
  const report = validateSovereignFormContracts();
  if (!report.valid) {
    throw new Error(`Sovereign form contracts invalid: ${report.errors.join(' | ')}`);
  }
}
