/**
 * Sovereign Action Contracts
 *
 * Defines authoritative action/button contracts for the Sovereign Studio.
 * These contracts are the single source of truth for action metadata including
 * accessibility attributes, test identifiers, and repository dependency requirements.
 */

export type ActionKind = 'primary' | 'secondary' | 'destructive' | 'diagnostic' | 'navigation';

export type SovereignActionContractId =
  | 'load-repo'
  | 'save-session'
  | 'restore-session'
  | 'clear-view'
  | 'analyze-mission'
  | 'start-task'
  | 'repair-log'
  | 'draft-pr'
  | 'monitor-toggle';

export interface SovereignActionContract {
  id: SovereignActionContractId;
  label: string;
  dataRole: string;
  testId: string;
  ariaLabel: string;
  kind: ActionKind;
  requiresRepo: boolean;
  canBeBusy: boolean;
}

export interface SovereignActionContractReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

const ACTION_DATA_ROLE_PATTERN = /^action-[a-z][a-z0-9-]*$/;
const ACTION_TEST_ID_PATTERN = /^[a-z][a-z0-9-]*__[a-z][a-z0-9-]*$/;
const REQUIRED_ACTION_IDS: SovereignActionContractId[] = [
  'load-repo',
  'save-session',
  'restore-session',
  'clear-view',
  'analyze-mission',
  'start-task',
  'repair-log',
  'draft-pr',
  'monitor-toggle',
];

/**
 * Load repository action contract.
 */
export const SOVEREIGN_ACTION_LOAD_REPO: SovereignActionContract = {
  id: 'load-repo',
  label: 'Load Repo',
  dataRole: 'action-load-repo',
  testId: 'repo-snapshot__load-repo',
  ariaLabel: 'Load Repo',
  kind: 'primary',
  requiresRepo: false,
  canBeBusy: true,
};

/**
 * Save session action contract.
 */
export const SOVEREIGN_ACTION_SAVE_SESSION: SovereignActionContract = {
  id: 'save-session',
  label: 'Save Session',
  dataRole: 'action-save-session',
  testId: 'repo-snapshot__save-session',
  ariaLabel: 'Save Session',
  kind: 'secondary',
  requiresRepo: true,
  canBeBusy: true,
};

/**
 * Restore session action contract.
 */
export const SOVEREIGN_ACTION_RESTORE_SESSION: SovereignActionContract = {
  id: 'restore-session',
  label: 'Restore Session',
  dataRole: 'action-restore-session',
  testId: 'repo-snapshot__restore-session',
  ariaLabel: 'Restore Session',
  kind: 'secondary',
  requiresRepo: false,
  canBeBusy: true,
};

/**
 * Clear view action contract.
 */
export const SOVEREIGN_ACTION_CLEAR_VIEW: SovereignActionContract = {
  id: 'clear-view',
  label: 'Clear View',
  dataRole: 'action-clear-view',
  testId: 'repo-snapshot__clear-view',
  ariaLabel: 'Clear View',
  kind: 'destructive',
  requiresRepo: false,
  canBeBusy: true,
};

/**
 * Analyze mission action contract.
 */
export const SOVEREIGN_ACTION_ANALYZE_MISSION: SovereignActionContract = {
  id: 'analyze-mission',
  label: 'Auftrag analysieren',
  dataRole: 'action-analyze-mission',
  testId: 'builder__analyze-mission',
  ariaLabel: 'Auftrag analysieren',
  kind: 'diagnostic',
  requiresRepo: true,
  canBeBusy: true,
};

/**
 * Start task action contract.
 */
export const SOVEREIGN_ACTION_START_TASK: SovereignActionContract = {
  id: 'start-task',
  label: 'Auftrag starten',
  dataRole: 'action-start-task',
  testId: 'builder__start-task',
  ariaLabel: 'Auftrag starten',
  kind: 'primary',
  requiresRepo: true,
  canBeBusy: true,
};

/**
 * Repair log action contract.
 */
export const SOVEREIGN_ACTION_REPAIR_LOG: SovereignActionContract = {
  id: 'repair-log',
  label: 'Fehlerlog reparieren',
  dataRole: 'action-repair-log',
  testId: 'builder__repair-log',
  ariaLabel: 'Fehlerlog reparieren',
  kind: 'diagnostic',
  requiresRepo: true,
  canBeBusy: true,
};

/**
 * Draft PR action contract.
 */
export const SOVEREIGN_ACTION_DRAFT_PR: SovereignActionContract = {
  id: 'draft-pr',
  label: 'Draft PR erstellen',
  dataRole: 'action-draft-pr',
  testId: 'builder__draft-pr',
  ariaLabel: 'Draft PR erstellen',
  kind: 'primary',
  requiresRepo: true,
  canBeBusy: true,
};

/**
 * Monitor toggle action contract.
 */
export const SOVEREIGN_ACTION_MONITOR_TOGGLE: SovereignActionContract = {
  id: 'monitor-toggle',
  label: 'Toggle Monitor',
  dataRole: 'action-monitor-toggle',
  testId: 'global-runtime-monitor__toggle',
  ariaLabel: 'Toggle runtime monitor visibility',
  kind: 'navigation',
  requiresRepo: false,
  canBeBusy: false,
};

export const SOVEREIGN_ACTION_CONTRACTS: SovereignActionContract[] = [
  SOVEREIGN_ACTION_LOAD_REPO,
  SOVEREIGN_ACTION_SAVE_SESSION,
  SOVEREIGN_ACTION_RESTORE_SESSION,
  SOVEREIGN_ACTION_CLEAR_VIEW,
  SOVEREIGN_ACTION_ANALYZE_MISSION,
  SOVEREIGN_ACTION_START_TASK,
  SOVEREIGN_ACTION_REPAIR_LOG,
  SOVEREIGN_ACTION_DRAFT_PR,
  SOVEREIGN_ACTION_MONITOR_TOGGLE,
];

function unique<T>(values: readonly T[]): T[] {
  return Array.from(new Set(values));
}

export function getSovereignActionContract(id: SovereignActionContractId): SovereignActionContract {
  const contract = SOVEREIGN_ACTION_CONTRACTS.find((candidate) => candidate.id === id);
  if (!contract) throw new Error(`Unknown Sovereign action contract: ${id}`);
  return contract;
}

export function validateSovereignActionContracts(): SovereignActionContractReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  const ids = SOVEREIGN_ACTION_CONTRACTS.map((contract) => contract.id);
  const dataRoles = SOVEREIGN_ACTION_CONTRACTS.map((contract) => contract.dataRole);
  const testIds = SOVEREIGN_ACTION_CONTRACTS.map((contract) => contract.testId);

  const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
  const duplicateRoles = dataRoles.filter((role, index) => dataRoles.indexOf(role) !== index);
  const duplicateTestIds = testIds.filter((testId, index) => testIds.indexOf(testId) !== index);

  if (duplicateIds.length) {
    errors.push(`Duplicate action contract ids: ${unique(duplicateIds).join(', ')}.`);
  }
  if (duplicateRoles.length) {
    errors.push(`Duplicate action contract data roles: ${unique(duplicateRoles).join(', ')}.`);
  }
  if (duplicateTestIds.length) {
    errors.push(`Duplicate action contract test ids: ${unique(duplicateTestIds).join(', ')}.`);
  }

  const validKinds: ActionKind[] = ['primary', 'secondary', 'destructive', 'diagnostic', 'navigation'];

  for (const contract of SOVEREIGN_ACTION_CONTRACTS) {
    if (!contract.id.trim()) {
      errors.push(`Action contract id must not be empty.`);
    }
    if (!contract.label.trim()) {
      errors.push(`${contract.id}: label must not be empty.`);
    }
    if (!contract.dataRole.trim()) {
      errors.push(`${contract.id}: dataRole must not be empty.`);
    }
    if (!ACTION_DATA_ROLE_PATTERN.test(contract.dataRole)) {
      errors.push(`${contract.id}: dataRole must match ${ACTION_DATA_ROLE_PATTERN}.`);
    }
    if (!contract.testId.trim()) {
      errors.push(`${contract.id}: testId must not be empty.`);
    }
    if (!ACTION_TEST_ID_PATTERN.test(contract.testId)) {
      errors.push(`${contract.id}: testId must match ${ACTION_TEST_ID_PATTERN}.`);
    }
    if (!contract.ariaLabel.trim()) {
      errors.push(`${contract.id}: ariaLabel must not be empty.`);
    }

    if (!validKinds.includes(contract.kind)) {
      errors.push(`${contract.id}: unknown action kind ${contract.kind}.`);
    }

    if (contract.id === 'analyze-mission' && contract.kind !== 'diagnostic') {
      errors.push('analyze-mission must be classified as diagnostic.');
    }
    if (contract.id === 'repair-log' && contract.kind !== 'diagnostic') {
      errors.push('repair-log must be classified as diagnostic.');
    }
    if (contract.id === 'clear-view' && !['secondary', 'destructive'].includes(contract.kind)) {
      errors.push('clear-view must be classified as secondary or destructive.');
    }
    if (contract.id === 'draft-pr' && !contract.requiresRepo) {
      errors.push('draft-pr must require a loaded repository.');
    }
  }

  for (const requiredId of REQUIRED_ACTION_IDS) {
    if (!ids.includes(requiredId)) {
      errors.push(`Missing required action contract: ${requiredId}.`);
    }
  }

  const repoDependentActions = SOVEREIGN_ACTION_CONTRACTS.filter((contract) => contract.requiresRepo);
  if (repoDependentActions.length < 5) {
    warnings.push('Fewer than 5 repository-dependent actions defined.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} action contract error(s), ${warnings.length} warning(s).`,
  };
}

export function assertSovereignActionContractsValid(): void {
  const report = validateSovereignActionContracts();
  if (!report.valid) {
    throw new Error(`Sovereign action contracts invalid: ${report.errors.join(' | ')}`);
  }
}
