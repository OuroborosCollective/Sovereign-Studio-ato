import {
  SOVEREIGN_PRODUCT_TEMPLATE,
  type SovereignProductTemplateTab,
} from './sovereignProductTemplate';

export interface SovereignTabStyleDefinition {
  tab: SovereignProductTemplateTab;
  cssClass: string;
  activeCssClass: string;
  dataRole: string;
  ariaLabel: string;
  mobilePriority: number;
}

export interface SovereignStyleContractValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export const SOVEREIGN_APP_CLASSES = {
  shell: 'sovereign-app-shell',
  title: 'sovereign-app-title',
  tabbar: 'sovereign-tabbar',
  tab: 'sovereign-tab',
  activeTab: 'sovereign-tab-active',
  card: 'sovereign-card',
  automationPanel: 'sovereign-automation-panel',
  select: 'sovereign-select',
  actionRow: 'sovereign-action-row',
  statusPill: 'sovereign-status-pill',
  diagnosticPanel: 'sovereign-diagnostic-panel',
} as const;

function createTabStyle(
  tab: SovereignProductTemplateTab,
  label: string,
  mobilePriority: number,
): SovereignTabStyleDefinition {
  return {
    tab,
    cssClass: `${SOVEREIGN_APP_CLASSES.tab} sovereign-tab-${tab}`,
    activeCssClass: SOVEREIGN_APP_CLASSES.activeTab,
    dataRole: `sovereign-tab-${tab}`,
    ariaLabel: `Open ${label} tab`,
    mobilePriority,
  };
}

export const SOVEREIGN_TAB_STYLE_CONTRACT: SovereignTabStyleDefinition[] = SOVEREIGN_PRODUCT_TEMPLATE.tabs.map((tab) =>
  createTabStyle(tab.id, tab.label, tab.mainFlowIndex ?? 10 + SOVEREIGN_PRODUCT_TEMPLATE.tabs.indexOf(tab)),
);

function unique(values: readonly string[]): string[] {
  return Array.from(new Set(values));
}

export function getSovereignTabStyle(tab: SovereignProductTemplateTab): SovereignTabStyleDefinition {
  const definition = SOVEREIGN_TAB_STYLE_CONTRACT.find((candidate) => candidate.tab === tab);
  if (!definition) throw new Error(`Unknown Sovereign tab style: ${tab}`);
  return definition;
}

export function validateSovereignStyleContract(): SovereignStyleContractValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const templateTabs = SOVEREIGN_PRODUCT_TEMPLATE.tabs.map((tab) => tab.id);
  const styleTabs = SOVEREIGN_TAB_STYLE_CONTRACT.map((style) => style.tab);
  const dataRoles = SOVEREIGN_TAB_STYLE_CONTRACT.map((style) => style.dataRole);

  for (const tab of templateTabs) {
    if (!styleTabs.includes(tab)) errors.push(`Missing tab style for ${tab}.`);
  }

  for (const tab of styleTabs) {
    if (!templateTabs.includes(tab)) errors.push(`Unknown tab style target ${tab}.`);
  }

  const duplicateRoles = dataRoles.filter((role, index) => dataRoles.indexOf(role) !== index);
  if (duplicateRoles.length) errors.push(`Duplicate tab style data roles: ${unique(duplicateRoles).join(', ')}.`);

  for (const style of SOVEREIGN_TAB_STYLE_CONTRACT) {
    if (!style.cssClass.includes(SOVEREIGN_APP_CLASSES.tab)) errors.push(`${style.tab} cssClass must include ${SOVEREIGN_APP_CLASSES.tab}.`);
    if (!style.cssClass.includes(`sovereign-tab-${style.tab}`)) errors.push(`${style.tab} cssClass must include sovereign-tab-${style.tab}.`);
    if (style.dataRole !== `sovereign-tab-${style.tab}`) errors.push(`${style.tab} dataRole must be sovereign-tab-${style.tab}.`);
    if (!style.ariaLabel.trim()) errors.push(`${style.tab} ariaLabel must not be empty.`);
    if (!Number.isInteger(style.mobilePriority) || style.mobilePriority < 0) errors.push(`${style.tab} mobilePriority must be a non-negative integer.`);
  }

  const primaryStyles = SOVEREIGN_PRODUCT_TEMPLATE.primaryFlow.map(getSovereignTabStyle);
  for (const [index, style] of primaryStyles.entries()) {
    if (style.mobilePriority !== index) errors.push(`Primary tab ${style.tab} mobilePriority must be ${index}.`);
  }

  if (SOVEREIGN_TAB_STYLE_CONTRACT.length !== SOVEREIGN_PRODUCT_TEMPLATE.tabs.length) {
    warnings.push('Tab style count does not match template tab count.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} style error(s), ${warnings.length} warning(s).`,
  };
}

export function assertSovereignStyleContractValid(): void {
  const report = validateSovereignStyleContract();
  if (!report.valid) throw new Error(`Sovereign style contract invalid: ${report.errors.join(' | ')}`);
}
