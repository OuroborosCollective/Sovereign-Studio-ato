export const SOVEREIGN_WORKSPACE_COMMAND_EVENT = 'sovereign:release-guide-command';

export const SOVEREIGN_WORKSPACE_TAB_IDS = [
  'builder',
  'repo',
  'files',
  'diff',
  'workflow',
  'repair',
  'remote',
  'memory',
  'telemetry',
  'monitor',
  'health',
  'runtime',
  'coverage',
  'findings',
] as const;

export type SovereignWorkspaceTab = typeof SOVEREIGN_WORKSPACE_TAB_IDS[number];
export type SovereignWorkspaceCommandType = 'back' | 'confirm' | 'next';
export type SovereignWorkspaceMenuGroup = 'primary' | 'work' | 'ops';

export interface SovereignWorkspaceCommandDetail {
  readonly type?: SovereignWorkspaceCommandType;
  readonly targetTab?: SovereignWorkspaceTab | null;
}

export interface SovereignWorkspaceMenuItem {
  readonly id: SovereignWorkspaceTab;
  readonly label: string;
  readonly hint: string;
  readonly group: SovereignWorkspaceMenuGroup;
}

export const SOVEREIGN_WORKSPACE_MENU: readonly SovereignWorkspaceMenuItem[] = [
  { id: 'builder', label: 'Chat', hint: 'Hauptfläche', group: 'primary' },
  { id: 'repo', label: 'Repo', hint: 'Quelle', group: 'primary' },
  { id: 'files', label: 'Files', hint: 'Review', group: 'primary' },
  { id: 'diff', label: 'Diff', hint: 'Änderungen', group: 'primary' },
  { id: 'workflow', label: 'Workflow', hint: 'CI Watch', group: 'work' },
  { id: 'repair', label: 'Repair', hint: 'Fixplan', group: 'work' },
  { id: 'remote', label: 'Remote', hint: 'Memory', group: 'work' },
  { id: 'monitor', label: 'Monitor', hint: 'Live', group: 'work' },
  { id: 'telemetry', label: 'Telemetry', hint: 'Events', group: 'ops' },
  { id: 'health', label: 'Health', hint: 'Status', group: 'ops' },
  { id: 'runtime', label: 'Runtime', hint: 'Steps', group: 'ops' },
  { id: 'coverage', label: 'Coverage', hint: 'Gates', group: 'ops' },
  { id: 'findings', label: 'Findings', hint: 'Scanner', group: 'ops' },
  { id: 'memory', label: 'Pattern', hint: 'Lernen', group: 'ops' },
] as const;

const WORKSPACE_TAB_SET = new Set<string>(SOVEREIGN_WORKSPACE_TAB_IDS);
const WORKSPACE_COMMAND_TYPES = new Set<string>(['back', 'confirm', 'next']);

export function isSovereignWorkspaceTab(value: unknown): value is SovereignWorkspaceTab {
  return typeof value === 'string' && WORKSPACE_TAB_SET.has(value);
}

export function isSovereignWorkspaceCommandType(value: unknown): value is SovereignWorkspaceCommandType {
  return typeof value === 'string' && WORKSPACE_COMMAND_TYPES.has(value);
}

export function createSovereignWorkspaceCommand(targetTab: SovereignWorkspaceTab, type: SovereignWorkspaceCommandType = 'next'): SovereignWorkspaceCommandDetail {
  return { type, targetTab };
}

export function normalizeSovereignWorkspaceCommandDetail(value: unknown): SovereignWorkspaceCommandDetail | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  const targetTab = record.targetTab;
  if (!isSovereignWorkspaceTab(targetTab)) return null;

  return {
    targetTab,
    type: isSovereignWorkspaceCommandType(record.type) ? record.type : 'next',
  };
}
