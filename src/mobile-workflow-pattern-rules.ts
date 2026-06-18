import type { MobileWorkbenchLamp, MobileWorkbenchMode, MobileWorkbenchTarget } from './mobile-workflow-orchestrator';

export type MobileWorkflowPatternId =
  | 'active-work'
  | 'result-review'
  | 'repo-setup'
  | 'runtime-healthy'
  | 'real-stopper'
  | 'awaiting-intent';

export interface MobileWorkflowPatternRule {
  id: MobileWorkflowPatternId;
  priority: number;
  lamp: MobileWorkbenchLamp;
  mode: MobileWorkbenchMode;
  targetNav: MobileWorkbenchTarget;
  autoOpenTarget: boolean;
  title: string;
  summary: string;
  positiveSignals: string[];
  negativeSignals?: string[];
  minScore: number;
  lines: string[];
}

export interface MobileWorkflowPatternMatch {
  rule: MobileWorkflowPatternRule;
  score: number;
  matchedSignals: string[];
}

export interface MobileWorkflowPatternValidationReport {
  valid: boolean;
  errors: string[];
  summary: string;
}

const VALID_LAMPS: MobileWorkbenchLamp[] = ['green', 'yellow', 'red'];
const VALID_MODES: MobileWorkbenchMode[] = ['nocode-plan', 'matrix-work', 'review-log', 'repair-log'];
const VALID_TARGETS: MobileWorkbenchTarget[] = ['Repo', 'Builder', 'Files', 'Diff', 'Live Monitor', 'Repair', null];

export const MOBILE_WORKFLOW_PATTERN_RULES: MobileWorkflowPatternRule[] = [
  {
    id: 'real-stopper',
    priority: 100,
    lamp: 'red',
    mode: 'repair-log',
    targetNav: 'Live Monitor',
    autoOpenTarget: true,
    title: 'Stopper erkannt',
    summary: 'Ich halte an und zeige dir automatisch die passende Log-Ansicht.',
    positiveSignals: ['validation_failed', 'package build failed', 'draft pr failed', 'build failed', 'workflow failed', 'critical blocker', 'blockierender fehler', 'fehlgeschlagen'],
    negativeSignals: ['0 failed', '0 failed step', 'no active step; 0 completed step(s), 0 failed step(s)', 'repair plan idle', 'workflow: idle'],
    minScore: 1,
    lines: ['pattern = real-stopper', 'open = log-view', 'next = rewrite-or-repair'],
  },
  {
    id: 'active-work',
    priority: 90,
    lamp: 'green',
    mode: 'matrix-work',
    targetNav: 'Live Monitor',
    autoOpenTarget: true,
    title: 'Ich arbeite',
    summary: 'Ich zeige den aktiven Arbeitsbereich und halte dich im Arbeitsmonitor auf dem Laufenden.',
    positiveSignals: ['läuft', 'running', 'busy', 'in progress', 'is building', 'is watching', 'package-build', 'diff-load', 'draft-pr-publish', 'workflow-watch'],
    minScore: 1,
    lines: ['pattern = active-work', 'observe = runtime-step', 'ui = follow-active-window'],
  },
  {
    id: 'result-review',
    priority: 80,
    lamp: 'green',
    mode: 'review-log',
    targetNav: 'Files',
    autoOpenTarget: true,
    title: 'Ergebnis bereit',
    summary: 'Die erzeugten Dateien sind bereit. Files und Diff sind jetzt die wichtigen Pruefpunkte.',
    positiveSignals: ['self review: accepted', 'generated-output-accepted', 'generated package passed self review', 'generated files review', 'pre-publish review', 'generated file'],
    minScore: 1,
    lines: ['pattern = result-review', 'files = ready', 'next = diff-or-draft-decision'],
  },
  {
    id: 'repo-setup',
    priority: 70,
    lamp: 'yellow',
    mode: 'nocode-plan',
    targetNav: 'Repo',
    autoOpenTarget: true,
    title: 'Repo fehlt',
    summary: 'Ich brauche zuerst die Repository URL. Oeffne das Zahnrad oder Repo und lade das Projekt.',
    positiveSignals: ['repo fehlt', 'repo snapshot required', 'repository snapshot is not ready', 'noch kein echtes repo', 'automation needs a loaded repository snapshot'],
    minScore: 1,
    lines: ['pattern = repo-setup', 'need = repository-url', 'next = load-repo'],
  },
  {
    id: 'runtime-healthy',
    priority: 60,
    lamp: 'green',
    mode: 'review-log',
    targetNav: null,
    autoOpenTarget: false,
    title: 'Checks gesund',
    summary: 'Runtime und Coverage sehen gesund aus. Du kannst weiter planen oder Dateien pruefen.',
    positiveSignals: ['runtime validation coverage', 'healthy', '21/21 runtime validation'],
    minScore: 1,
    lines: ['pattern = runtime-healthy', 'state = stable', 'next = continue-main-flow'],
  },
  {
    id: 'awaiting-intent',
    priority: 1,
    lamp: 'yellow',
    mode: 'nocode-plan',
    targetNav: 'Builder',
    autoOpenTarget: false,
    title: 'Bereit fuer Auftrag',
    summary: 'Schreib deinen Wunsch in einfachen Worten. Ich plane danach automatisch und zeige die Arbeit live.',
    positiveSignals: [''],
    minScore: 0,
    lines: ['pattern = awaiting-intent', 'need = user-goal', 'guard = draft-only'],
  },
];

function includesSignal(source: string, signal: string): boolean {
  if (signal === '') return true;
  return source.includes(signal.toLowerCase());
}

export function validateMobileWorkflowPatternRule(rule: MobileWorkflowPatternRule): MobileWorkflowPatternValidationReport {
  const errors: string[] = [];
  if (!rule.id) errors.push('Pattern id is required.');
  if (!Number.isFinite(rule.priority)) errors.push(`Pattern ${rule.id} priority must be finite.`);
  if (!VALID_LAMPS.includes(rule.lamp)) errors.push(`Pattern ${rule.id} has unknown lamp.`);
  if (!VALID_MODES.includes(rule.mode)) errors.push(`Pattern ${rule.id} has unknown mode.`);
  if (!VALID_TARGETS.includes(rule.targetNav)) errors.push(`Pattern ${rule.id} has unknown target.`);
  if (rule.autoOpenTarget && !rule.targetNav) errors.push(`Pattern ${rule.id} auto-open requires target.`);
  if (!rule.title.trim()) errors.push(`Pattern ${rule.id} title is required.`);
  if (!rule.summary.trim()) errors.push(`Pattern ${rule.id} summary is required.`);
  if (!Array.isArray(rule.positiveSignals) || rule.positiveSignals.length === 0) errors.push(`Pattern ${rule.id} needs positive signals.`);
  if (!Number.isFinite(rule.minScore) || rule.minScore < 0) errors.push(`Pattern ${rule.id} minScore must be non-negative.`);
  if (!Array.isArray(rule.lines) || rule.lines.length === 0) errors.push(`Pattern ${rule.id} needs workbench lines.`);
  return { valid: errors.length === 0, errors, summary: `${errors.length} pattern validation error(s).` };
}

export function assertMobileWorkflowPatternRulesValid(rules = MOBILE_WORKFLOW_PATTERN_RULES): void {
  const errors = rules.flatMap((rule) => validateMobileWorkflowPatternRule(rule).errors);
  const ids = new Set<string>();
  for (const rule of rules) {
    if (ids.has(rule.id)) errors.push(`Duplicate pattern id: ${rule.id}`);
    ids.add(rule.id);
  }
  if (!rules.some((rule) => rule.id === 'awaiting-intent')) errors.push('Fallback pattern awaiting-intent is required.');
  if (errors.length) throw new Error(`Mobile workflow pattern rules invalid: ${errors.join(' | ')}`);
}

export function matchMobileWorkflowPattern(visibleText: string, rules = MOBILE_WORKFLOW_PATTERN_RULES): MobileWorkflowPatternMatch {
  assertMobileWorkflowPatternRulesValid(rules);
  const source = visibleText.toLowerCase();
  const matches = rules
    .map((rule): MobileWorkflowPatternMatch | null => {
      if (rule.negativeSignals?.some((signal) => includesSignal(source, signal))) return null;
      const matchedSignals = rule.positiveSignals.filter((signal) => includesSignal(source, signal));
      const score = matchedSignals.length;
      return score >= rule.minScore ? { rule, score, matchedSignals } : null;
    })
    .filter((match): match is MobileWorkflowPatternMatch => Boolean(match))
    .sort((a, b) => b.rule.priority - a.rule.priority || b.score - a.score);
  const fallback = rules.find((rule) => rule.id === 'awaiting-intent');
  if (!matches.length && fallback) return { rule: fallback, score: 0, matchedSignals: [] };
  if (!matches.length) throw new Error('No mobile workflow pattern matched and no fallback pattern exists.');
  return matches[0];
}
