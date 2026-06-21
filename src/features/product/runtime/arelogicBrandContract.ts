import { SOVEREIGN_APP_CLASSES } from './sovereignStyleContract';
import {
  SOVEREIGN_APP_SHELL_CONTRACT,
  SOVEREIGN_TABBAR_CONTRACT,
  SOVEREIGN_ACTION_BUTTON_CONTRACT,
  type SovereignComponentContract,
} from './sovereignComponentContracts';

export type ArelogicBrandPriority =
  | 'runtime-contracts'
  | 'accessibility-contracts'
  | 'component-contracts'
  | 'brand-visual-layer';

export interface ArelogicBrandToken {
  name: string;
  cssVariable: string;
  value: string;
  purpose: string;
}

export interface ArelogicBrandClass {
  name: string;
  purpose: string;
  attachesTo: string[];
}

export interface ArelogicBrandContractReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export const ARELOGIC_BRAND_PRIORITY: ArelogicBrandPriority[] = [
  'runtime-contracts',
  'accessibility-contracts',
  'component-contracts',
  'brand-visual-layer',
];

export const ARELOGIC_BRAND_TOKENS: ArelogicBrandToken[] = [
  { name: 'Void', cssVariable: '--are-void', value: '#050816', purpose: 'deep runtime background' },
  { name: 'Deep', cssVariable: '--are-deep', value: '#080D1E', purpose: 'panel underlay' },
  { name: 'Surface', cssVariable: '--are-surface', value: '#0C1428', purpose: 'cards and panels' },
  { name: 'Overlay', cssVariable: '--are-overlay', value: '#111B35', purpose: 'hover and active layers' },
  { name: 'Ion', cssVariable: '--are-ion', value: '#00C8FF', purpose: 'runtime and technical accent' },
  { name: 'Matter', cssVariable: '--are-matter', value: '#7B5EA7', purpose: 'sovereign and truth context accent' },
  { name: 'Signal', cssVariable: '--are-signal', value: '#00FF9C', purpose: 'online and successful state' },
  { name: 'Warn', cssVariable: '--are-warn', value: '#F59E0B', purpose: 'warning and pending state' },
  { name: 'Danger', cssVariable: '--are-danger', value: '#FF4466', purpose: 'blocked and critical state' },
];

export const ARELOGIC_BRAND_CLASSES: ArelogicBrandClass[] = [
  {
    name: 'arelogic-runtime-surface',
    purpose: 'applies deep runtime background and subtle grid language',
    attachesTo: [SOVEREIGN_APP_CLASSES.shell],
  },
  {
    name: 'arelogic-panel-frame',
    purpose: 'adds corner brackets and low-glow panel identity without changing state ownership',
    attachesTo: [SOVEREIGN_APP_CLASSES.card, SOVEREIGN_APP_CLASSES.automationPanel, SOVEREIGN_APP_CLASSES.diagnosticPanel],
  },
  {
    name: 'arelogic-hud-label',
    purpose: 'uses all-caps HUD label grammar for secondary labels only',
    attachesTo: ['headings', 'eyebrows', 'status captions'],
  },
  {
    name: 'arelogic-status-badge',
    purpose: 'adds branded status badge styling while preserving aria and data-state contracts',
    attachesTo: [SOVEREIGN_APP_CLASSES.statusPill],
  },
  {
    name: 'arelogic-action-surface',
    purpose: 'adds ion/matter visual treatment to action controls without replacing button contracts',
    attachesTo: [SOVEREIGN_ACTION_BUTTON_CONTRACT.rootClass],
  },
];

export const ARELOGIC_BRAND_COMPONENTS: SovereignComponentContract[] = [
  SOVEREIGN_APP_SHELL_CONTRACT,
  SOVEREIGN_TABBAR_CONTRACT,
  SOVEREIGN_ACTION_BUTTON_CONTRACT,
];

const HEX_COLOR_PATTERN = /^#[0-9A-F]{6}$/;

function unique(values: readonly string[]): string[] {
  return Array.from(new Set(values));
}

export function validateArelogicBrandContract(): ArelogicBrandContractReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const priority = ARELOGIC_BRAND_PRIORITY.join('>');

  if (priority !== 'runtime-contracts>accessibility-contracts>component-contracts>brand-visual-layer') {
    errors.push('ARELogic brand priority must keep brand-visual-layer last.');
  }

  const tokenVariables = ARELOGIC_BRAND_TOKENS.map((token) => token.cssVariable);
  const duplicateTokenVariables = tokenVariables.filter((token, index) => tokenVariables.indexOf(token) !== index);
  if (duplicateTokenVariables.length) errors.push(`Duplicate ARELogic token variables: ${unique(duplicateTokenVariables).join(', ')}.`);

  for (const token of ARELOGIC_BRAND_TOKENS) {
    if (!token.cssVariable.startsWith('--are-')) errors.push(`${token.name} token must use --are- namespace.`);
    if (!HEX_COLOR_PATTERN.test(token.value)) errors.push(`${token.name} token must be a six-digit uppercase hex color.`);
    if (!token.purpose.trim()) errors.push(`${token.name} token purpose must not be empty.`);
  }

  for (const brandClass of ARELOGIC_BRAND_CLASSES) {
    if (!brandClass.name.startsWith('arelogic-')) errors.push(`${brandClass.name} must use arelogic- namespace.`);
    if (!brandClass.purpose.trim()) errors.push(`${brandClass.name} purpose must not be empty.`);
    if (!brandClass.attachesTo.length) errors.push(`${brandClass.name} must declare at least one attachment target.`);
  }

  const knownComponentRoots = ARELOGIC_BRAND_COMPONENTS.map((contract) => contract.rootClass);
  for (const rootClass of knownComponentRoots) {
    if (!rootClass.startsWith('sovereign-')) errors.push(`Brand layer must attach to Sovereign component contracts, got ${rootClass}.`);
  }

  if (!ARELOGIC_BRAND_TOKENS.some((token) => token.cssVariable === '--are-ion')) {
    errors.push('ARELogic brand must expose --are-ion.');
  }

  if (!ARELOGIC_BRAND_TOKENS.some((token) => token.cssVariable === '--are-matter')) {
    errors.push('ARELogic brand must expose --are-matter.');
  }

  if (ARELOGIC_BRAND_CLASSES.length < 4) {
    warnings.push('ARELogic brand layer should expose shell, panel, HUD and badge classes.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} brand error(s), ${warnings.length} warning(s).`,
  };
}

export function assertArelogicBrandContractValid(): void {
  const report = validateArelogicBrandContract();
  if (!report.valid) throw new Error(`ARELogic brand contract invalid: ${report.errors.join(' | ')}`);
}
