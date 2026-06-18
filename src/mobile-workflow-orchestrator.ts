import { matchMobileWorkflowPattern } from './mobile-workflow-pattern-rules';

export type MobileWorkbenchLamp = 'green' | 'yellow' | 'red';
export type MobileWorkbenchMode = 'nocode-plan' | 'matrix-work' | 'review-log' | 'repair-log';
export type MobileWorkbenchTarget = 'Repo' | 'Builder' | 'Files' | 'Diff' | 'Live Monitor' | 'Repair' | null;

export interface MobileWorkflowOrchestratorInput {
  visibleText: string;
}

export interface MobileWorkflowOrchestratorDecision {
  lamp: MobileWorkbenchLamp;
  mode: MobileWorkbenchMode;
  title: string;
  summary: string;
  targetNav: MobileWorkbenchTarget;
  autoOpenTarget: boolean;
  lines: string[];
}

export interface MobileWorkflowValidationReport {
  valid: boolean;
  errors: string[];
  summary: string;
}

const LAMPS: MobileWorkbenchLamp[] = ['green', 'yellow', 'red'];
const MODES: MobileWorkbenchMode[] = ['nocode-plan', 'matrix-work', 'review-log', 'repair-log'];
const TARGETS: MobileWorkbenchTarget[] = ['Repo', 'Builder', 'Files', 'Diff', 'Live Monitor', 'Repair', null];
const MAX_VISIBLE_TEXT = 20000;
const MAX_UI_TEXT = 240;

const SAFE_FALLBACK: MobileWorkflowOrchestratorDecision = {
  lamp: 'yellow',
  mode: 'nocode-plan',
  title: 'Arbeitsfluss pruefen',
  summary: 'Ich konnte den aktuellen Zustand nicht sicher lesen. Bitte oeffne Repo oder Live Monitor.',
  targetNav: 'Repo',
  autoOpenTarget: false,
  lines: ['state.read = guarded', 'fallback = safe', 'next = repo_or_monitor'],
};

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.slice(0, MAX_VISIBLE_TEXT) : '';
}

function trimUi(value: string): string {
  return value.trim().slice(0, MAX_UI_TEXT);
}

function sanitizeDecision(decision: MobileWorkflowOrchestratorDecision): MobileWorkflowOrchestratorDecision {
  return {
    lamp: LAMPS.includes(decision.lamp) ? decision.lamp : SAFE_FALLBACK.lamp,
    mode: MODES.includes(decision.mode) ? decision.mode : SAFE_FALLBACK.mode,
    title: trimUi(decision.title) || SAFE_FALLBACK.title,
    summary: trimUi(decision.summary) || SAFE_FALLBACK.summary,
    targetNav: TARGETS.includes(decision.targetNav) ? decision.targetNav : null,
    autoOpenTarget: Boolean(decision.autoOpenTarget),
    lines: Array.isArray(decision.lines)
      ? decision.lines.map((line) => trimUi(String(line))).filter(Boolean).slice(0, 8)
      : SAFE_FALLBACK.lines,
  };
}

export function validateMobileWorkflowDecision(decision: MobileWorkflowOrchestratorDecision): MobileWorkflowValidationReport {
  const errors: string[] = [];

  if (!LAMPS.includes(decision.lamp)) errors.push(`Unknown lamp: ${decision.lamp}`);
  if (!MODES.includes(decision.mode)) errors.push(`Unknown mode: ${decision.mode}`);
  if (!TARGETS.includes(decision.targetNav)) errors.push(`Unknown target: ${String(decision.targetNav)}`);
  if (!decision.title.trim()) errors.push('Title is required.');
  if (!decision.summary.trim()) errors.push('Summary is required.');
  if (!Array.isArray(decision.lines) || decision.lines.length === 0) errors.push('At least one workbench line is required.');
  if (decision.autoOpenTarget && !decision.targetNav) errors.push('Auto-open requires a target.');

  return {
    valid: errors.length === 0,
    errors,
    summary: `${errors.length} mobile workflow validation error(s).`,
  };
}

export function assertMobileWorkflowDecisionValid(decision: MobileWorkflowOrchestratorDecision): void {
  const report = validateMobileWorkflowDecision(decision);
  if (!report.valid) throw new Error(`Mobile workflow decision invalid: ${report.errors.join(' | ')}`);
}

function safeDecision(decision: MobileWorkflowOrchestratorDecision): MobileWorkflowOrchestratorDecision {
  const sanitized = sanitizeDecision(decision);
  assertMobileWorkflowDecisionValid(sanitized);
  return sanitized;
}

function targetFromPattern(id: string, source: string, fallback: MobileWorkbenchTarget): MobileWorkbenchTarget {
  if (id !== 'active-work') return fallback;
  const text = source.toLowerCase();
  if (text.includes('repo-load') || text.includes('repository load') || text.includes('loading repository tree')) return 'Repo';
  if (text.includes('package-build') || text.includes('package build') || text.includes('building sovereign package')) return 'Builder';
  if (text.includes('diff-load') || text.includes('diff source load')) return 'Diff';
  if (text.includes('draft-pr-publish') || text.includes('draft pr publish') || text.includes('workflow-watch') || text.includes('workflow watch')) return 'Live Monitor';
  if (text.includes('repair-plan') || text.includes('repair mission')) return 'Repair';
  return fallback;
}

export function decideMobileWorkflow(input: MobileWorkflowOrchestratorInput): MobileWorkflowOrchestratorDecision {
  try {
    const source = normalizeText(input.visibleText);
    const match = matchMobileWorkflowPattern(source);
    const targetNav = targetFromPattern(match.rule.id, source, match.rule.targetNav);
    return safeDecision({
      lamp: match.rule.lamp,
      mode: match.rule.mode,
      title: match.rule.title,
      summary: match.rule.summary,
      targetNav,
      autoOpenTarget: match.rule.autoOpenTarget,
      lines: [
        `pattern = ${match.rule.id}`,
        `score = ${match.score}`,
        ...match.rule.lines,
      ],
    });
  } catch {
    return safeDecision(SAFE_FALLBACK);
  }
}
