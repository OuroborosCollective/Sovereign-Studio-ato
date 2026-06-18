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

function hasAny(source: string, tokens: string[]): boolean {
  const text = source.toLowerCase();
  return tokens.some((token) => text.includes(token.toLowerCase()));
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

function hasHarmlessFailureText(source: string): boolean {
  return hasAny(source, [
    '0 failed',
    '0 failed step',
    'no active step; 0 completed step(s), 0 failed step(s)',
    'repair plan idle',
    'workflow: idle',
  ]);
}

function hasRealStopper(source: string): boolean {
  if (hasHarmlessFailureText(source)) return false;
  return hasAny(source, [
    'validation_failed',
    'package build failed',
    'draft pr failed',
    'build failed',
    'workflow failed',
    'critical blocker',
    'blockierender fehler',
    'fehlgeschlagen',
  ]);
}

function workTarget(source: string): MobileWorkbenchTarget {
  if (hasAny(source, ['repo-load', 'repository load', 'loading repository tree'])) return 'Repo';
  if (hasAny(source, ['package-build', 'package build', 'building sovereign package', 'full auto is building'])) return 'Builder';
  if (hasAny(source, ['diff-load', 'diff source load', 'loading source snapshots'])) return 'Diff';
  if (hasAny(source, ['draft-pr-publish', 'draft pr publish', 'creating github branch'])) return 'Live Monitor';
  if (hasAny(source, ['workflow-watch', 'workflow watch', 'watching github commit checks'])) return 'Live Monitor';
  if (hasAny(source, ['repair-plan', 'repair mission'])) return 'Repair';
  return 'Live Monitor';
}

export function decideMobileWorkflow(input: MobileWorkflowOrchestratorInput): MobileWorkflowOrchestratorDecision {
  const source = normalizeText(input.visibleText);

  if (hasRealStopper(source)) {
    return safeDecision({
      lamp: 'red',
      mode: 'repair-log',
      title: 'Stopper erkannt',
      summary: 'Ich halte an und zeige dir automatisch die Fehleransicht.',
      targetNav: 'Live Monitor',
      autoOpenTarget: true,
      lines: ['stopper.scan = true', 'open(log_view)', 'next.action = explain_and_rewrite'],
    });
  }

  if (hasAny(source, ['läuft', 'running', 'busy', 'in progress', 'is building', 'is watching'])) {
    const target = workTarget(source);
    return safeDecision({
      lamp: 'green',
      mode: 'matrix-work',
      title: 'Ich arbeite',
      summary: `Ich zeige den aktiven Arbeitsbereich: ${target ?? 'Monitor'}.`,
      targetNav: target,
      autoOpenTarget: true,
      lines: ['scan(repo_state)', 'validate(runtime_guards)', 'execute(active_step)', 'ui.follow(active_window)'],
    });
  }

  if (hasAny(source, ['self review: accepted', 'generated-output-accepted', 'generated package passed self review'])) {
    return safeDecision({
      lamp: 'green',
      mode: 'review-log',
      title: 'Ergebnis bereit',
      summary: 'Die erzeugten Dateien sind akzeptiert. Ich zeige Files; Diff ist der naechste Check.',
      targetNav: 'Files',
      autoOpenTarget: true,
      lines: ['self_review = accepted', 'files.ready = true', 'next = diff_or_draft_decision'],
    });
  }

  if (hasAny(source, ['generated files review', 'pre-publish review', 'generated file'])) {
    return safeDecision({
      lamp: 'green',
      mode: 'review-log',
      title: 'Dateien pruefen',
      summary: 'Ich habe Dateien vorbereitet. Pruefe Files und Diff vor dem Draft PR.',
      targetNav: 'Files',
      autoOpenTarget: true,
      lines: ['generated.files = present', 'review.required = true', 'next = human_confirmation'],
    });
  }

  if (hasAny(source, ['repo fehlt', 'repo snapshot required', 'repository snapshot is not ready', 'noch kein echtes repo', 'automation needs a loaded repository snapshot'])) {
    return safeDecision({
      lamp: 'yellow',
      mode: 'nocode-plan',
      title: 'Repo fehlt',
      summary: 'Ich brauche zuerst die Repository URL. Oeffne das Zahnrad oder Repo und lade das Projekt.',
      targetNav: 'Repo',
      autoOpenTarget: true,
      lines: ['need.repo_url = true', 'next = load_repo', 'full_auto.wait = setup'],
    });
  }

  if (hasAny(source, ['runtime validation coverage', 'healthy', '21/21 runtime validation'])) {
    return safeDecision({
      lamp: 'green',
      mode: 'review-log',
      title: 'Checks gesund',
      summary: 'Runtime und Coverage sehen gesund aus. Du kannst weiter planen oder Dateien pruefen.',
      targetNav: null,
      autoOpenTarget: false,
      lines: ['runtime.coverage = healthy', 'blocking_errors = 0', 'flow.ready = true'],
    });
  }

  return safeDecision({
    lamp: 'yellow',
    mode: 'nocode-plan',
    title: 'Bereit fuer Auftrag',
    summary: 'Schreib deinen Wunsch in einfachen Worten. Ich plane dann automatisch und zeige die Arbeit live.',
    targetNav: 'Builder',
    autoOpenTarget: false,
    lines: ['awaiting.user_intent = true', 'full_auto.guard = draft_only', 'next = describe_goal'],
  });
}
