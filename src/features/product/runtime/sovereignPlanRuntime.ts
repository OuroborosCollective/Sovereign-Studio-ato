/**
 * Sovereign Plan Runtime
 *
 * A compact plan-state runtime inspired by agent planning loops, but adapted to
 * Sovereign rules: no percentage progress, no fake completion, and every step
 * exposes the next allowed action.
 */

export type SovereignPlanStepStatus =
  | 'not_started'
  | 'in_progress'
  | 'completed'
  | 'blocked';

export type SovereignPlanNextAction =
  | 'start_step'
  | 'continue_step'
  | 'resolve_blocker'
  | 'finish_plan'
  | 'none';

export interface SovereignPlanStep {
  readonly id: string;
  readonly title: string;
  readonly status: SovereignPlanStepStatus;
  readonly notes: readonly string[];
  readonly artifacts: readonly string[];
  readonly blocker?: string;
  readonly updatedAt: number;
}

export interface SovereignPlan {
  readonly id: string;
  readonly title: string;
  readonly steps: readonly SovereignPlanStep[];
  readonly createdAt: number;
  readonly updatedAt: number;
}

export interface SovereignPlanSummary {
  readonly completed: number;
  readonly inProgress: number;
  readonly blocked: number;
  readonly notStarted: number;
  readonly total: number;
  readonly nextStepId: string | null;
  readonly nextAllowedAction: SovereignPlanNextAction;
  readonly text: string;
}

export interface CreateSovereignPlanInput {
  readonly id?: string;
  readonly title: string;
  readonly steps: readonly string[];
  readonly now?: number;
}

function cleanText(value: string, fallback: string): string {
  const clean = value.trim().replace(/\s+/g, ' ');
  return clean || fallback;
}

function normalizeId(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || 'item';
}

function uniqueStepId(existing: Set<string>, title: string, index: number): string {
  const base = normalizeId(title) || `step-${index + 1}`;
  let candidate = `${index + 1}-${base}`;
  let suffix = 2;
  while (existing.has(candidate)) {
    candidate = `${index + 1}-${base}-${suffix}`;
    suffix += 1;
  }
  existing.add(candidate);
  return candidate;
}

export function createSovereignPlan(input: CreateSovereignPlanInput): SovereignPlan {
  const now = input.now ?? Date.now();
  const id = normalizeId(input.id ?? input.title);
  const seen = new Set<string>();
  const steps = input.steps
    .map((step, index) => cleanText(step, `Schritt ${index + 1}`))
    .filter((step) => step.length > 0)
    .map((step, index): SovereignPlanStep => ({
      id: uniqueStepId(seen, step, index),
      title: step,
      status: 'not_started',
      notes: [],
      artifacts: [],
      updatedAt: now,
    }));

  return {
    id,
    title: cleanText(input.title, 'Sovereign Plan'),
    steps,
    createdAt: now,
    updatedAt: now,
  };
}

function updateStep(
  plan: SovereignPlan,
  stepId: string,
  updater: (step: SovereignPlanStep) => SovereignPlanStep,
  now = Date.now(),
): SovereignPlan {
  let found = false;
  const steps = plan.steps.map((step) => {
    if (step.id !== stepId) return step;
    found = true;
    return updater({ ...step, updatedAt: now });
  });

  if (!found) return plan;

  return {
    ...plan,
    steps,
    updatedAt: now,
  };
}

export function getSovereignPlanNextStep(plan: SovereignPlan): SovereignPlanStep | null {
  return plan.steps.find((step) =>
    step.status === 'in_progress' || step.status === 'not_started',
  ) ?? null;
}

export function markSovereignPlanStepInProgress(
  plan: SovereignPlan,
  stepId: string,
  note?: string,
  now = Date.now(),
): SovereignPlan {
  return updateStep(plan, stepId, (step) => ({
    ...step,
    status: 'in_progress',
    notes: note ? [...step.notes, note] : step.notes,
    blocker: undefined,
  }), now);
}

export function completeSovereignPlanStep(
  plan: SovereignPlan,
  stepId: string,
  note?: string,
  artifact?: string,
  now = Date.now(),
): SovereignPlan {
  return updateStep(plan, stepId, (step) => ({
    ...step,
    status: 'completed',
    notes: note ? [...step.notes, note] : step.notes,
    artifacts: artifact ? [...step.artifacts, artifact] : step.artifacts,
    blocker: undefined,
  }), now);
}

export function blockSovereignPlanStep(
  plan: SovereignPlan,
  stepId: string,
  blocker: string,
  note?: string,
  now = Date.now(),
): SovereignPlan {
  return updateStep(plan, stepId, (step) => ({
    ...step,
    status: 'blocked',
    blocker: cleanText(blocker, 'blocked'),
    notes: note ? [...step.notes, note] : step.notes,
  }), now);
}

export function deriveSovereignPlanNextAction(plan: SovereignPlan): SovereignPlanNextAction {
  if (plan.steps.some((step) => step.status === 'blocked')) return 'resolve_blocker';
  if (plan.steps.some((step) => step.status === 'in_progress')) return 'continue_step';
  if (plan.steps.some((step) => step.status === 'not_started')) return 'start_step';
  if (plan.steps.length > 0 && plan.steps.every((step) => step.status === 'completed')) return 'finish_plan';
  return 'none';
}

export function summarizeSovereignPlan(plan: SovereignPlan): SovereignPlanSummary {
  const completed = plan.steps.filter((step) => step.status === 'completed').length;
  const inProgress = plan.steps.filter((step) => step.status === 'in_progress').length;
  const blocked = plan.steps.filter((step) => step.status === 'blocked').length;
  const notStarted = plan.steps.filter((step) => step.status === 'not_started').length;
  const nextStep = getSovereignPlanNextStep(plan);
  const nextAllowedAction = deriveSovereignPlanNextAction(plan);
  const statusMark: Record<SovereignPlanStepStatus, string> = {
    completed: '[✓]',
    in_progress: '[→]',
    blocked: '[!]',
    not_started: '[ ]',
  };

  const lines = [
    `Plan: ${plan.title}`,
    `Status: ${completed} completed, ${inProgress} in progress, ${blocked} blocked, ${notStarted} not started`,
    'Steps:',
    ...plan.steps.map((step, index) => {
      const blocker = step.blocker ? ` · Blocker: ${step.blocker}` : '';
      return `${index + 1}. ${statusMark[step.status]} ${step.title}${blocker}`;
    }),
  ];

  return {
    completed,
    inProgress,
    blocked,
    notStarted,
    total: plan.steps.length,
    nextStepId: nextStep?.id ?? null,
    nextAllowedAction,
    text: lines.join('\n'),
  };
}

export function createSovereignPlanFromRequest(request: string, now = Date.now()): SovereignPlan {
  const title = cleanText(request, 'Sovereign Auftrag').slice(0, 96);
  return createSovereignPlan({
    id: `request-${now}`,
    title,
    now,
    steps: [
      'Auftrag verstehen',
      'Runtime-Gates prüfen',
      'Erlaubten Executor wählen',
      'Ergebnis beobachten',
      'Nächste erlaubte Aktion ableiten',
    ],
  });
}
