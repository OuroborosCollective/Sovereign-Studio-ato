export type MobileWorkbenchLamp = 'green' | 'yellow' | 'red';
export type MobileWorkbenchMode = 'nocode-plan' | 'matrix-work' | 'review-log' | 'repair-log';

export interface MobileWorkflowOrchestratorInput {
  visibleText: string;
}

export interface MobileWorkflowOrchestratorDecision {
  lamp: MobileWorkbenchLamp;
  mode: MobileWorkbenchMode;
  title: string;
  summary: string;
  targetNav: 'Repo' | 'Builder' | 'Files' | 'Diff' | 'Live Monitor' | 'Repair' | null;
  autoOpenTarget: boolean;
  lines: string[];
}

function hasAny(source: string, tokens: string[]): boolean {
  const text = source.toLowerCase();
  return tokens.some((token) => text.includes(token.toLowerCase()));
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

function workTarget(source: string): MobileWorkflowOrchestratorDecision['targetNav'] {
  if (hasAny(source, ['repo-load', 'repository load', 'loading repository tree'])) return 'Repo';
  if (hasAny(source, ['package-build', 'package build', 'building sovereign package', 'full auto is building'])) return 'Builder';
  if (hasAny(source, ['diff-load', 'diff source load', 'loading source snapshots'])) return 'Diff';
  if (hasAny(source, ['draft-pr-publish', 'draft pr publish', 'creating github branch'])) return 'Live Monitor';
  if (hasAny(source, ['workflow-watch', 'workflow watch', 'watching github commit checks'])) return 'Live Monitor';
  if (hasAny(source, ['repair-plan', 'repair mission'])) return 'Repair';
  return 'Live Monitor';
}

export function decideMobileWorkflow(input: MobileWorkflowOrchestratorInput): MobileWorkflowOrchestratorDecision {
  const source = input.visibleText;

  if (hasRealStopper(source)) {
    return {
      lamp: 'red',
      mode: 'repair-log',
      title: 'Stopper erkannt',
      summary: 'Ich halte an und zeige dir automatisch die Fehleransicht.',
      targetNav: 'Live Monitor',
      autoOpenTarget: true,
      lines: ['stopper.scan = true', 'open(log_view)', 'next.action = explain_and_rewrite'],
    };
  }

  if (hasAny(source, ['läuft', 'running', 'busy', 'in progress', 'is building', 'is watching'])) {
    const target = workTarget(source);
    return {
      lamp: 'green',
      mode: 'matrix-work',
      title: 'Ich arbeite',
      summary: `Ich zeige den aktiven Arbeitsbereich: ${target ?? 'Monitor'}.`,
      targetNav: target,
      autoOpenTarget: true,
      lines: ['scan(repo_state)', 'validate(runtime_guards)', 'execute(active_step)', 'ui.follow(active_window)'],
    };
  }

  if (hasAny(source, ['self review: accepted', 'generated-output-accepted', 'generated package passed self review'])) {
    return {
      lamp: 'green',
      mode: 'review-log',
      title: 'Ergebnis bereit',
      summary: 'Die erzeugten Dateien sind akzeptiert. Ich zeige Files; Diff ist der naechste Check.',
      targetNav: 'Files',
      autoOpenTarget: true,
      lines: ['self_review = accepted', 'files.ready = true', 'next = diff_or_draft_decision'],
    };
  }

  if (hasAny(source, ['generated files review', 'pre-publish review', 'generated file'])) {
    return {
      lamp: 'green',
      mode: 'review-log',
      title: 'Dateien pruefen',
      summary: 'Ich habe Dateien vorbereitet. Pruefe Files und Diff vor dem Draft PR.',
      targetNav: 'Files',
      autoOpenTarget: true,
      lines: ['generated.files = present', 'review.required = true', 'next = human_confirmation'],
    };
  }

  if (hasAny(source, ['repo fehlt', 'repo snapshot required', 'repository snapshot is not ready', 'noch kein echtes repo', 'automation needs a loaded repository snapshot'])) {
    return {
      lamp: 'yellow',
      mode: 'nocode-plan',
      title: 'Repo fehlt',
      summary: 'Ich brauche zuerst die Repository URL. Oeffne das Zahnrad oder Repo und lade das Projekt.',
      targetNav: 'Repo',
      autoOpenTarget: true,
      lines: ['need.repo_url = true', 'next = load_repo', 'full_auto.wait = setup'],
    };
  }

  if (hasAny(source, ['runtime validation coverage', 'healthy', '21/21 runtime validation'])) {
    return {
      lamp: 'green',
      mode: 'review-log',
      title: 'Checks gesund',
      summary: 'Runtime und Coverage sehen gesund aus. Du kannst weiter planen oder Dateien pruefen.',
      targetNav: null,
      autoOpenTarget: false,
      lines: ['runtime.coverage = healthy', 'blocking_errors = 0', 'flow.ready = true'],
    };
  }

  return {
    lamp: 'yellow',
    mode: 'nocode-plan',
    title: 'Bereit fuer Auftrag',
    summary: 'Schreib deinen Wunsch in einfachen Worten. Ich plane dann automatisch und zeige die Arbeit live.',
    targetNav: 'Builder',
    autoOpenTarget: false,
    lines: ['awaiting.user_intent = true', 'full_auto.guard = draft_only', 'next = describe_goal'],
  };
}
