export type SovereignContainerId = 'repo-snapshot' | 'builder' | 'global-runtime-monitor';

export interface SovereignContainerContract {
  id: SovereignContainerId;
  label: string;
  rootClass: string;
  dataRole: string;
  testId: string;
  ariaLabel: string;
}

export interface SovereignContainerContractReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export const SOVEREIGN_CONTAINER_CONTRACTS: SovereignContainerContract[] = [
  {
    id: 'repo-snapshot',
    label: 'Repository Snapshot',
    rootClass: 'sovereign-card sovereign-container sovereign-repo-container',
    dataRole: 'sovereign-container-repo-snapshot',
    testId: 'repo-snapshot-container',
    ariaLabel: 'Repository Snapshot',
  },
  {
    id: 'builder',
    label: 'Builder',
    rootClass: 'sovereign-card sovereign-container sovereign-builder-container',
    dataRole: 'sovereign-container-builder',
    testId: 'builder-container',
    ariaLabel: 'Sovereign Builder',
  },
  {
    id: 'global-runtime-monitor',
    label: 'Global Runtime Monitor',
    rootClass: 'sovereign-global-monitor sovereign-container sovereign-monitor-container',
    dataRole: 'sovereign-container-global-runtime-monitor',
    testId: 'global-runtime-monitor',
    ariaLabel: 'Sovereign global runtime monitor',
  },
];

const TEST_ID_PATTERN = /^[a-z][a-z0-9-]*(-[a-z0-9]+)*$/;
const DATA_ROLE_PATTERN = /^sovereign-container-[a-z0-9-]+$/;

function unique(values: readonly string[]): string[] {
  return Array.from(new Set(values));
}

export function getSovereignContainerContract(id: SovereignContainerId): SovereignContainerContract {
  const contract = SOVEREIGN_CONTAINER_CONTRACTS.find((candidate) => candidate.id === id);
  if (!contract) throw new Error(`Unknown Sovereign container contract: ${id}`);
  return contract;
}

export function validateSovereignContainerContracts(): SovereignContainerContractReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const ids = SOVEREIGN_CONTAINER_CONTRACTS.map((contract) => contract.id);
  const roles = SOVEREIGN_CONTAINER_CONTRACTS.map((contract) => contract.dataRole);
  const testIds = SOVEREIGN_CONTAINER_CONTRACTS.map((contract) => contract.testId);

  const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
  const duplicateRoles = roles.filter((role, index) => roles.indexOf(role) !== index);
  const duplicateTestIds = testIds.filter((testId, index) => testIds.indexOf(testId) !== index);

  if (duplicateIds.length) errors.push(`Duplicate container ids: ${unique(duplicateIds).join(', ')}.`);
  if (duplicateRoles.length) errors.push(`Duplicate container data roles: ${unique(duplicateRoles).join(', ')}.`);
  if (duplicateTestIds.length) errors.push(`Duplicate container test ids: ${unique(duplicateTestIds).join(', ')}.`);

  for (const contract of SOVEREIGN_CONTAINER_CONTRACTS) {
    if (!contract.label.trim()) errors.push(`${contract.id} label must not be empty.`);
    if (!contract.rootClass.includes('sovereign-container')) errors.push(`${contract.id} rootClass must include sovereign-container.`);
    if (!contract.rootClass.includes('sovereign-')) errors.push(`${contract.id} rootClass must use Sovereign namespace.`);
    if (!DATA_ROLE_PATTERN.test(contract.dataRole)) errors.push(`${contract.id} dataRole must use sovereign-container-* pattern.`);
    if (!TEST_ID_PATTERN.test(contract.testId)) errors.push(`${contract.id} testId must be kebab-case.`);
    if (!contract.ariaLabel.trim()) errors.push(`${contract.id} ariaLabel must not be empty.`);
  }

  const required = ['repo-snapshot', 'builder', 'global-runtime-monitor'] as const;
  for (const id of required) {
    if (!ids.includes(id)) errors.push(`Missing required container contract: ${id}.`);
  }

  if (SOVEREIGN_CONTAINER_CONTRACTS.length < required.length) {
    warnings.push('Container contract list is smaller than the required product surface set.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} container contract error(s), ${warnings.length} warning(s).`,
  };
}

export function assertSovereignContainerContractsValid(): void {
  const report = validateSovereignContainerContracts();
  if (!report.valid) throw new Error(`Sovereign container contracts invalid: ${report.errors.join(' | ')}`);
}
