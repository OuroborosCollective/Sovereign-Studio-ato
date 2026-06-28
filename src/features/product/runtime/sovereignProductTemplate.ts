export type SovereignProductTemplateTab =
  | 'repo'
  | 'builder'
  | 'chat'
  | 'files'
  | 'diff'
  | 'workflow'
  | 'repair'
  | 'remote'
  | 'memory'
  | 'telemetry'
  | 'monitor'
  | 'readiness'
  | 'integrity'
  | 'findings'
  | 'health'
  | 'runtime'
  | 'coverage';

export type SovereignProductTemplateTabGroup = 'primary' | 'side' | 'diagnostic';

export type SovereignProductTemplatePhase =
  | 'repo-setup'
  | 'intent-planning'
  | 'package-review'
  | 'diff-review'
  | 'draft-pr-workflow'
  | 'repair-diagnostics'
  | 'operator-diagnostics';

export type SovereignProductTemplateAutoNavigationReason =
  | 'active-work'
  | 'red-stopper'
  | 'passive-review'
  | 'awaiting-intent'
  | 'side-channel'
  | 'manual';

export interface SovereignProductTemplateTabDefinition {
  id: SovereignProductTemplateTab;
  label: string;
  group: SovereignProductTemplateTabGroup;
  phase: SovereignProductTemplatePhase;
  mainFlowIndex: number | null;
  autoOpenAllowed: boolean;
  userVisible: boolean;
}

export interface SovereignProductTemplateContract {
  version: 1;
  productName: 'Sovereign Studio';
  startTab: SovereignProductTemplateTab;
  primaryFlow: SovereignProductTemplateTab[];
  sideTabs: SovereignProductTemplateTab[];
  diagnosticTabs: SovereignProductTemplateTab[];
  tabs: SovereignProductTemplateTabDefinition[];
  autoNavigationAllowlist: SovereignProductTemplateAutoNavigationReason[];
  invariants: string[];
}

export interface SovereignProductTemplateValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export const SOVEREIGN_PRODUCT_TRUTH_INVARIANTS = [
  'Default surface is Chat.',
  'The user talks to Sovereign; Sovereign operates the control room behind the curtain.',
  'Only chat timeline, text input, small thinking/status cues and compact lamps are visible by default.',
  'Repo, Files, Diff, Workflow, Runtime, Telemetry, Health, Coverage, Memory and Inspector are inspection surfaces opened explicitly, never forced on the user.',
  'Repo setup may start from a chat instruction.',
  'The UI must not become a dashboard, monitor or second control shell.',
  'Truth is produced by runtime, not by UI.',
] as const;

export const SOVEREIGN_PRODUCT_TEMPLATE: SovereignProductTemplateContract = {
  version: 1,
  productName: 'Sovereign Studio',
  startTab: 'builder',
  primaryFlow: ['repo', 'builder', 'files', 'diff'],
  sideTabs: ['workflow', 'repair', 'remote', 'memory', 'telemetry', 'monitor'],
  diagnosticTabs: ['chat', 'readiness', 'integrity', 'findings', 'health', 'runtime', 'coverage'],
  autoNavigationAllowlist: ['active-work', 'red-stopper'],
  invariants: [
    ...SOVEREIGN_PRODUCT_TRUTH_INVARIANTS,
    'Builder is the startup surface because it is the official NoCode chat workbench.',
    'There must be only one visible chat workbench in the primary flow: the Builder tab labelled Chat.',
    'Repo remains the first setup surface in the primary flow and may be requested by the chat when missing.',
    'Files and Diff are review surfaces, not startup surfaces.',
    'Workflow and Repair are side/stopper surfaces, not passive planning fallbacks.',
    'The Android primary navigation is Repo, Chat, Files and Diff only.',
    'The legacy Chat AI runtime panel is diagnostic-only and must not be a second user-facing chat surface.',
    'Passive review, awaiting-intent and side-channel states must not auto-open tabs.',
    'Only active work or red stopper states may auto-open a target view.',
    'Coach, setup drawer and workbench are guidance layers; they must not become state sources for themselves.',
  ],
  tabs: [
    { id: 'repo', label: 'Repo', group: 'primary', phase: 'repo-setup', mainFlowIndex: 0, autoOpenAllowed: true, userVisible: true },
    { id: 'builder', label: 'Chat', group: 'primary', phase: 'intent-planning', mainFlowIndex: 1, autoOpenAllowed: false, userVisible: true },
    { id: 'files', label: 'Files', group: 'primary', phase: 'package-review', mainFlowIndex: 2, autoOpenAllowed: false, userVisible: true },
    { id: 'diff', label: 'Diff', group: 'primary', phase: 'diff-review', mainFlowIndex: 3, autoOpenAllowed: false, userVisible: true },
    { id: 'workflow', label: 'Workflow', group: 'side', phase: 'draft-pr-workflow', mainFlowIndex: null, autoOpenAllowed: true, userVisible: true },
    { id: 'repair', label: 'Repair', group: 'side', phase: 'repair-diagnostics', mainFlowIndex: null, autoOpenAllowed: true, userVisible: true },
    { id: 'remote', label: 'Remote Memory', group: 'side', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
    { id: 'memory', label: 'Pattern Memory', group: 'side', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
    { id: 'telemetry', label: 'Telemetry', group: 'side', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
    { id: 'monitor', label: 'Live Monitor', group: 'side', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: true, userVisible: true },
    { id: 'chat', label: 'Chat AI Diagnostics', group: 'diagnostic', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: false },
    { id: 'readiness', label: 'Readiness', group: 'diagnostic', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
    { id: 'integrity', label: 'Integrity', group: 'diagnostic', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
    { id: 'findings', label: 'Findings', group: 'diagnostic', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
    { id: 'health', label: 'Health', group: 'diagnostic', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
    { id: 'runtime', label: 'Runtime', group: 'diagnostic', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
    { id: 'coverage', label: 'Coverage', group: 'diagnostic', phase: 'operator-diagnostics', mainFlowIndex: null, autoOpenAllowed: false, userVisible: true },
  ],
};

function unique<T>(values: readonly T[]): T[] {
  return Array.from(new Set(values));
}

function tabIds(contract: SovereignProductTemplateContract): SovereignProductTemplateTab[] {
  return contract.tabs.map((tab) => tab.id);
}

function missingFromContract(contract: SovereignProductTemplateContract, expected: SovereignProductTemplateTab[]): SovereignProductTemplateTab[] {
  const known = new Set(tabIds(contract));
  return expected.filter((tab) => !known.has(tab));
}

export function getSovereignProductTemplateTab(tab: SovereignProductTemplateTab): SovereignProductTemplateTabDefinition {
  const definition = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((candidate) => candidate.id === tab);
  if (!definition) throw new Error(`Unknown Sovereign product template tab: ${tab}`);
  return definition;
}

export function isSovereignProductTemplatePrimaryTab(tab: SovereignProductTemplateTab): boolean {
  return getSovereignProductTemplateTab(tab).group === 'primary';
}

export function canSovereignProductTemplateAutoOpen(reason: SovereignProductTemplateAutoNavigationReason): boolean {
  return SOVEREIGN_PRODUCT_TEMPLATE.autoNavigationAllowlist.includes(reason);
}

export function validateSovereignProductTemplate(
  contract: SovereignProductTemplateContract = SOVEREIGN_PRODUCT_TEMPLATE,
): SovereignProductTemplateValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const ids = tabIds(contract);
  const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);

  if (contract.version !== 1) errors.push('Template version must be 1.');
  if (contract.productName !== 'Sovereign Studio') errors.push('Template productName must be Sovereign Studio.');
  if (contract.startTab !== 'builder') errors.push('Template must start in builder chat workbench tab.');
  if (duplicateIds.length) errors.push(`Duplicate template tabs: ${unique(duplicateIds).join(', ')}`);

  for (const invariant of SOVEREIGN_PRODUCT_TRUTH_INVARIANTS) {
    if (!contract.invariants.includes(invariant)) {
      errors.push(`Missing product truth invariant: ${invariant}`);
    }
  }

  const primaryMissing = missingFromContract(contract, contract.primaryFlow);
  const sideMissing = missingFromContract(contract, contract.sideTabs);
  const diagnosticMissing = missingFromContract(contract, contract.diagnosticTabs);
  if (primaryMissing.length) errors.push(`Primary flow references unknown tabs: ${primaryMissing.join(', ')}`);
  if (sideMissing.length) errors.push(`Side tabs reference unknown tabs: ${sideMissing.join(', ')}`);
  if (diagnosticMissing.length) errors.push(`Diagnostic tabs reference unknown tabs: ${diagnosticMissing.join(', ')}`);

  if (contract.primaryFlow.join('>') !== 'repo>builder>files>diff') {
    errors.push('Primary flow must be repo > builder > files > diff.');
  }

  const builderTab = contract.tabs.find((candidate) => candidate.id === 'builder');
  if (builderTab?.label !== 'Chat') errors.push('Builder tab label must be Chat because it is the official chat workbench.');

  const chatTab = contract.tabs.find((candidate) => candidate.id === 'chat');
  if (chatTab && (chatTab.group === 'primary' || chatTab.userVisible)) {
    errors.push('Legacy Chat AI tab must stay diagnostic-only and hidden from primary navigation.');
  }

  for (const [index, tab] of contract.primaryFlow.entries()) {
    const definition = contract.tabs.find((candidate) => candidate.id === tab);
    if (!definition) continue;
    if (definition.group !== 'primary') errors.push(`Primary flow tab ${tab} must be group primary.`);
    if (definition.mainFlowIndex !== index) errors.push(`Primary flow tab ${tab} must have mainFlowIndex ${index}.`);
  }

  for (const tab of [...contract.sideTabs, ...contract.diagnosticTabs]) {
    const definition = contract.tabs.find((candidate) => candidate.id === tab);
    if (!definition) continue;
    if (definition.mainFlowIndex !== null) errors.push(`Non-primary tab ${tab} must not have mainFlowIndex.`);
  }

  for (const reason of ['passive-review', 'awaiting-intent', 'side-channel', 'manual'] as const) {
    if (contract.autoNavigationAllowlist.includes(reason)) {
      errors.push(`${reason} must not be allowed to auto-open views.`);
    }
  }

  for (const reason of ['active-work', 'red-stopper'] as const) {
    if (!contract.autoNavigationAllowlist.includes(reason)) {
      errors.push(`${reason} must be allowed to auto-open views.`);
    }
  }

  const tabCount = contract.primaryFlow.length + contract.sideTabs.length + contract.diagnosticTabs.length;
  if (tabCount !== contract.tabs.length) {
    warnings.push('Tab groups do not cover every declared tab exactly once.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} template error(s), ${warnings.length} warning(s).`,
  };
}

export function assertSovereignProductTemplateValid(
  contract: SovereignProductTemplateContract = SOVEREIGN_PRODUCT_TEMPLATE,
): void {
  const report = validateSovereignProductTemplate(contract);
  if (!report.valid) throw new Error(`Sovereign product template invalid: ${report.errors.join(' | ')}`);
}
